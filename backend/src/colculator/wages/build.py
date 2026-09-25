"""Build FR4 state and metro wage artifacts from official BLS OEWS files."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree


TABLES_URL = "https://www.bls.gov/oes/tables.htm"
SOURCE = "bls_oews"
OCCUPATIONS = {
    "15-1251": "Computer Programmers",
    "15-1252": "Software Developers",
    "15-1253": "Software Quality Assurance Analysts and Testers",
    "15-1254": "Web Developers",
    "15-1255": "Web and Digital Interface Designers",
}
ARCHIVE_KINDS = {
    "state": ("st", "state_M{year}_dl.xlsx", "US-STATE-", {"2", "3"}),
    "metro": ("ma", "MSA_M{year}_dl.xlsx", "US-METRO-", {"4"}),
}
USER_AGENT = "Colculator OEWS ingestion/0.1 (https://github.com/JSakMad/Colculator)"
XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


@dataclass(frozen=True)
class BuildConfig:
    regions_json: Path
    output_json: Path
    sources_json: Path
    seed_sql: Path | None = None
    cache_dir: Path = Path(".cache/wages")
    state_archive: Path | None = None
    metro_archive: Path | None = None
    year: int | None = None


def _request(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(f"Unable to download official BLS file {url}: {last_error}")


def _archive_url(year: int, kind: str) -> str:
    suffix = ARCHIVE_KINDS[kind][0]
    return f"https://www.bls.gov/oes/special-requests/oesm{year % 100:02d}{suffix}.zip"


def _default_year(cache_dir: Path) -> int:
    state_years = {
        2000 + int(match.group(1))
        for path in cache_dir.glob("oesm??st.zip")
        if (match := re.fullmatch(r"oesm(\d{2})st\.zip", path.name))
    }
    metro_years = {
        2000 + int(match.group(1))
        for path in cache_dir.glob("oesm??ma.zip")
        if (match := re.fullmatch(r"oesm(\d{2})ma\.zip", path.name))
    }
    cached = state_years & metro_years
    if cached:
        return max(cached)
    # The late-May workflow runs after BLS publishes estimates for May of the
    # preceding year. The workbook release label is validated before output.
    return datetime.date.today().year - 1


def _load_archive(path: Path | None, url: str, cache_dir: Path) -> tuple[bytes, Path]:
    if path is not None:
        return path.read_bytes(), path
    cache_path = cache_dir / url.rsplit("/", 1)[-1]
    if not cache_path.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(_request(url))
    return cache_path.read_bytes(), cache_path


def _column(reference: str) -> str:
    match = re.match(r"[A-Z]+", reference)
    if match is None:
        raise ValueError(f"Invalid XLSX cell reference: {reference}")
    return match.group()


def _xlsx_rows(content: bytes) -> Iterable[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
            shared = [
                "".join(node.text or "" for node in item.iter(XLSX_NS + "t"))
                for item in root.iter(XLSX_NS + "si")
            ]
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        raw_rows: list[dict[str, str]] = []
        for row in sheet.iter(XLSX_NS + "row"):
            values: dict[str, str] = {}
            for cell in row.findall(XLSX_NS + "c"):
                value_node = cell.find(XLSX_NS + "v")
                value = "" if value_node is None else value_node.text or ""
                if cell.attrib.get("t") == "s" and value:
                    value = shared[int(value)]
                elif cell.attrib.get("t") == "inlineStr":
                    value = "".join(
                        node.text or "" for node in cell.iter(XLSX_NS + "t")
                    )
                values[_column(cell.attrib["r"])] = value
            raw_rows.append(values)
    if not raw_rows:
        raise ValueError("BLS workbook is empty")
    columns = {column: name.strip() for column, name in raw_rows[0].items()}
    required = {"AREA", "AREA_TYPE", "I_GROUP", "OCC_CODE", "O_GROUP", "A_MEAN", "A_MEDIAN"}
    if not required <= set(columns.values()):
        raise ValueError(f"BLS workbook is missing columns: {sorted(required - set(columns.values()))}")
    for raw in raw_rows[1:]:
        yield {name: raw.get(column, "").strip() for column, name in columns.items()}


def _workbook(archive: bytes, expected_name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        matches = [name for name in source.namelist() if name.endswith(expected_name)]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one {expected_name} in BLS archive")
        return source.read(matches[0])


def _annual_wage(raw: str) -> tuple[int | None, str]:
    value = raw.strip()
    if value == "*":
        return None, "not_available"
    if value == "#":
        return None, "top_coded"
    if not value:
        return None, "not_reported"
    try:
        number = Decimal(value.replace(",", ""))
    except InvalidOperation as error:
        raise ValueError(f"Unexpected BLS annual wage: {raw!r}") from error
    if number <= 0 or number != number.to_integral_value():
        raise ValueError(f"BLS annual wage must be a positive whole dollar: {raw!r}")
    return int(number), "published"


def _records(
    workbook: bytes,
    *,
    kind: str,
    year: int,
    valid_regions: set[str],
) -> list[dict[str, object]]:
    _, _, prefix, area_types = ARCHIVE_KINDS[kind]
    records: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for row in _xlsx_rows(workbook):
        if row["OCC_CODE"] not in OCCUPATIONS:
            continue
        if row["I_GROUP"] != "cross-industry" or row["O_GROUP"] != "detailed":
            raise ValueError(f"Unexpected BLS grouping for {row['OCC_CODE']}")
        if row["AREA_TYPE"] not in area_types:
            raise ValueError(f"Unexpected BLS area type {row['AREA_TYPE']} in {kind} file")
        region_id = prefix + row["AREA"]
        if region_id not in valid_regions:
            # Official files also contain Puerto Rico and other territories, which
            # are outside the FR1 50-states-plus-DC catalog.
            continue
        key = (region_id, row["OCC_CODE"])
        if key in seen:
            raise ValueError(f"Duplicate BLS wage row for {region_id} {row['OCC_CODE']}")
        seen.add(key)
        mean_wage, mean_status = _annual_wage(row["A_MEAN"])
        median_wage, median_status = _annual_wage(row["A_MEDIAN"])
        records.append(
            {
                "region_id": region_id,
                "soc_code": row["OCC_CODE"],
                "median_wage": median_wage,
                "mean_wage": mean_wage,
                "median_wage_status": median_status,
                "mean_wage_status": mean_status,
                "year": year,
                "source": SOURCE,
            }
        )
    return records


def _write_json(path: Path, payload: object, *, compact: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        if compact:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")


def _sql_literal(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _write_seed(path: Path, records: list[dict[str, object]]) -> None:
    columns = (
        "region_id",
        "soc_code",
        "median_wage",
        "mean_wage",
        "median_wage_status",
        "mean_wage_status",
        "year",
        "source",
    )
    rows = [
        "(" + ",".join(_sql_literal(record[column]) for column in columns) + ")"
        for record in records
    ]
    updates = ",\n  ".join(
        f"{column} = excluded.{column}"
        for column in columns
        if column not in {"region_id", "soc_code", "year"}
    )
    sql = (
        "-- Generated by `npm run build:wages`; do not edit by hand.\n"
        "begin;\n\n"
        f"insert into public.wage_benchmarks ({', '.join(columns)})\nvalues\n  "
        + ",\n  ".join(rows)
        + "\non conflict (region_id, soc_code, year) do update set\n  "
        + updates
        + ";\n\ncommit;\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql, encoding="utf-8")


def build_wages(config: BuildConfig) -> dict[str, int]:
    catalog = json.loads(config.regions_json.read_text(encoding="utf-8"))
    regions = catalog.get("regions")
    if not isinstance(regions, list):
        raise ValueError("Region catalog does not contain a regions list")
    valid_regions = {
        str(region["id"])
        for region in regions
        if isinstance(region, dict) and region.get("type") in {"state", "metro"}
    }

    year = config.year if config.year is not None else _default_year(config.cache_dir)
    urls = {kind: _archive_url(year, kind) for kind in ARCHIVE_KINDS}

    archive_paths = {"state": config.state_archive, "metro": config.metro_archive}
    archives: dict[str, bytes] = {}
    input_paths: dict[str, Path] = {}
    records: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for kind, (_, workbook_pattern, _, _) in ARCHIVE_KINDS.items():
        archive, input_path = _load_archive(archive_paths[kind], urls[kind], config.cache_dir)
        archives[kind] = archive
        input_paths[kind] = input_path
        subset = _records(
            _workbook(archive, workbook_pattern.format(year=year)),
            kind=kind,
            year=year,
            valid_regions=valid_regions,
        )
        records.extend(subset)
        counts[kind] = len(subset)

    records.sort(key=lambda record: (str(record["region_id"]), str(record["soc_code"])))
    if not records or set(record["soc_code"] for record in records) != set(OCCUPATIONS):
        raise ValueError("BLS files do not contain all five required software occupations")

    _write_json(
        config.output_json,
        {
            "schema_version": 1,
            "year": year,
            "source": SOURCE,
            "occupations": OCCUPATIONS,
            "records": records,
        },
        compact=True,
    )
    _write_json(
        config.sources_json,
        {
            "publisher": "U.S. Bureau of Labor Statistics",
            "program": "Occupational Employment and Wage Statistics",
            "release": f"May {year}",
            "tables_url": TABLES_URL,
            "archives": {
                kind: {
                    "url": urls[kind],
                    "sha256": hashlib.sha256(archives[kind]).hexdigest(),
                    "downloaded_filename": input_paths[kind].name,
                }
                for kind in ARCHIVE_KINDS
            },
            "occupations": OCCUPATIONS,
            "source_tag": SOURCE,
            "suppression_markers": {
                "*": "not_available",
                "#": "top_coded_at_or_above_the_bls_publication_threshold",
            },
            "notes": (
                "The five detailed occupations are the complete official 15-1250 "
                "broad-group membership. Only published annual mean and median wages "
                "are stored; unavailable or top-coded values remain null with an "
                "explicit status. Territories outside the FR1 region catalog are excluded."
            ),
            "record_counts": counts,
        },
        compact=False,
    )
    if config.seed_sql is not None:
        _write_seed(config.seed_sql, records)
    return {"year": year, "records": len(records), **counts}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions-json", type=Path, default=Path("frontend/public/data/regions.json"))
    parser.add_argument("--output-json", type=Path, default=Path("frontend/public/data/wages.json"))
    parser.add_argument("--sources-json", type=Path, default=Path("frontend/public/data/wages.sources.json"))
    parser.add_argument("--seed-sql", type=Path, default=Path("supabase/seeds/wages.sql"))
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/wages"))
    parser.add_argument("--state-archive", type=Path)
    parser.add_argument("--metro-archive", type=Path)
    parser.add_argument("--year", type=int)
    return parser.parse_args()


def main() -> None:
    arguments = _parse_args()
    result = build_wages(
        BuildConfig(
            regions_json=arguments.regions_json,
            output_json=arguments.output_json,
            sources_json=arguments.sources_json,
            seed_sql=arguments.seed_sql,
            cache_dir=arguments.cache_dir,
            state_archive=arguments.state_archive,
            metro_archive=arguments.metro_archive,
            year=arguments.year,
        )
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
