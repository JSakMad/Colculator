"""Build the FR1 region hierarchy and browser-ready TopoJSON assets.

Inputs are pinned official Census TIGER/Line and Census-hosted OMB files. The
pipeline deliberately has no third-party Python dependencies; lockfile-pinned
Node libraries perform Shapefile decoding and TopoJSON conversion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree


TIGER_VINTAGE = 2025
OMB_DELINEATION_VINTAGE = "2023-07"
SUPPORTED_STATE_FIPS_UPPER_BOUND = 60
SIMPLIFICATION_PERCENT = "2%"
TOPOJSON_QUANTIZATION = 100_000


@dataclass(frozen=True)
class Source:
    key: str
    filename: str
    url: str
    sha256: str
    publisher: str
    vintage: str


SOURCES = (
    Source(
        key="tiger_states",
        filename="tl_2025_us_state.zip",
        url="https://www2.census.gov/geo/tiger/TIGER2025/STATE/tl_2025_us_state.zip",
        sha256="59a220888a8d9be8117c4fcd38f542bd02d81abf0d198c78113595ad540dd957",
        publisher="U.S. Census Bureau",
        vintage="2025",
    ),
    Source(
        key="tiger_counties",
        filename="tl_2025_us_county.zip",
        url="https://www2.census.gov/geo/tiger/TIGER2025/COUNTY/tl_2025_us_county.zip",
        sha256="9c6e9d9076abce2670d1de255de3710c35ecca00a7005d88e012dec52d95f763",
        publisher="U.S. Census Bureau",
        vintage="2025",
    ),
    Source(
        key="omb_delineation",
        filename="list1_2023.xlsx",
        url=(
            "https://www2.census.gov/programs-surveys/metro-micro/geographies/"
            "reference-files/2023/delineation-files/list1_2023.xlsx"
        ),
        sha256="952c4b1e78acbb54e6ec9412434b7602fedacbf021736351a63c181bdb753629",
        publisher="U.S. Office of Management and Budget via U.S. Census Bureau",
        vintage=OMB_DELINEATION_VINTAGE,
    ),
)


@dataclass(frozen=True)
class BuildConfig:
    cache_dir: Path
    output_dir: Path
    geometry_script: Path
    seed_sql: Path | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(source: Source, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / source.filename
    if destination.exists() and _sha256(destination) == source.sha256:
        return destination

    request = urllib.request.Request(
        source.url,
        headers={"User-Agent": "Colculator region ingestion/0.1"},
    )
    temporary = destination.with_suffix(destination.suffix + ".partial")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
        actual = _sha256(temporary)
        if actual != source.sha256:
            raise ValueError(
                f"Checksum mismatch for {source.key}: expected {source.sha256}, got {actual}"
            )
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise ValueError(f"Unsafe archive member: {member.filename}")
        zipped.extractall(destination)


_SPREADSHEET_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
}


def _xlsx_rows(path: Path) -> Iterable[dict[str, str]]:
    """Read the first XLSX worksheet using only the Python standard library."""

    with zipfile.ZipFile(path) as workbook:
        shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
        shared = [
            "".join(node.text or "" for node in item.findall(".//main:t", _SPREADSHEET_NS))
            for item in shared_root.findall("main:si", _SPREADSHEET_NS)
        ]
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))

    rows: list[dict[str, str]] = []
    for row in sheet.findall(".//main:row", _SPREADSHEET_NS):
        values: dict[str, str] = {}
        for cell in row.findall("main:c", _SPREADSHEET_NS):
            match = re.match(r"[A-Z]+", cell.attrib["r"])
            value_node = cell.find("main:v", _SPREADSHEET_NS)
            if match is None or value_node is None or value_node.text is None:
                continue
            value = value_node.text
            if cell.attrib.get("t") == "s":
                value = shared[int(value)]
            values[match.group()] = value.strip()
        rows.append(values)

    if len(rows) < 4:
        raise ValueError("OMB workbook did not contain the documented header and data rows")
    headers = rows[2]
    for row in rows[3:]:
        yield {
            headers[column]: value
            for column, value in row.items()
            if column in headers and headers[column]
        }


def _metropolitan_membership(
    workbook: Path,
) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    county_to_metro: dict[str, str] = {}
    metros: dict[str, dict[str, object]] = {}
    for row in _xlsx_rows(workbook):
        if row.get("Metropolitan/Micropolitan Statistical Area") != "Metropolitan Statistical Area":
            continue
        state_fips = row.get("FIPS State Code", "").zfill(2)
        county_part = row.get("FIPS County Code", "").zfill(3)
        cbsa_code = row.get("CBSA Code", "").zfill(5)
        if not (state_fips.isdigit() and county_part.isdigit() and cbsa_code.isdigit()):
            raise ValueError(f"Invalid official OMB delineation row: {row}")
        if int(state_fips) >= SUPPORTED_STATE_FIPS_UPPER_BOUND:
            continue
        county_fips = state_fips + county_part
        metro_id = f"US-METRO-{cbsa_code}"
        existing = county_to_metro.setdefault(county_fips, metro_id)
        if existing != metro_id:
            raise ValueError(f"County {county_fips} belongs to more than one MSA")
        metros[metro_id] = {
            "id": metro_id,
            "country_code": "US",
            "type": "metro",
            "fips": cbsa_code,
            "name": row["CBSA Title"],
            "parent_region_id": None,
            "msa_id": None,
            "geometry_ref": None,
            "is_interactive": True,
        }
    return county_to_metro, metros


def _run_geometry_script(script: Path, *arguments: str) -> None:
    subprocess.run(
        ["node", str(script), *arguments],
        check=True,
        text=True,
    )


def _load_feature_collection(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as stream:
        collection = json.load(stream)
    if collection.get("type") != "FeatureCollection":
        raise ValueError(f"Expected a GeoJSON FeatureCollection in {path}")
    return collection


def _write_json(path: Path, value: object, *, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        if compact:
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")


def _sql_literal(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return "'" + str(value).replace("'", "''") + "'"


def _write_region_seed(path: Path, regions: list[dict[str, object]]) -> None:
    columns = (
        "id",
        "country_code",
        "type",
        "fips",
        "name",
        "parent_region_id",
        "msa_id",
        "geometry_ref",
        "is_interactive",
    )
    rows = [
        "(" + ",".join(_sql_literal(region[column]) for column in columns) + ")"
        for region in regions
    ]
    updates = ",\n  ".join(
        f"{column} = excluded.{column}" for column in columns if column != "id"
    )
    sql = (
        "-- Generated by `npm run build:regions`; do not edit by hand.\n"
        "begin;\n\n"
        f"insert into public.regions ({', '.join(columns)})\nvalues\n  "
        + ",\n  ".join(rows)
        + "\non conflict (id) do update set\n  "
        + updates
        + ";\n\ncommit;\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql, encoding="utf-8")


def _state_properties(properties: dict[str, object]) -> dict[str, object]:
    fips = str(properties["GEOID"])
    return {
        "id": f"US-STATE-{fips}",
        "country_code": "US",
        "type": "state",
        "fips": fips,
        "name": str(properties["NAME"]),
        "parent_region_id": None,
        "msa_id": None,
        "geometry_ref": f"/data/geometry/us-states.topo.json#states/{fips}",
        "is_interactive": True,
        "abbreviation": str(properties["STUSPS"]),
    }


def _county_properties(
    properties: dict[str, object], county_to_metro: dict[str, str]
) -> dict[str, object]:
    fips = str(properties["GEOID"])
    state_fips = str(properties["STATEFP"])
    return {
        "id": f"US-COUNTY-{fips}",
        "country_code": "US",
        "type": "county",
        "fips": fips,
        "name": str(properties["NAME"]),
        "parent_region_id": f"US-STATE-{state_fips}",
        "msa_id": county_to_metro.get(fips),
        "geometry_ref": f"/data/geometry/us-counties.topo.json#counties/{fips}",
        "is_interactive": True,
    }


def _enrich_features(
    collection: dict[str, object],
    property_builder,
) -> list[dict[str, object]]:
    features = collection["features"]
    if not isinstance(features, list):
        raise ValueError("GeoJSON features must be a list")
    regions: list[dict[str, object]] = []
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            raise ValueError("Every GeoJSON feature must have properties")
        properties = property_builder(feature["properties"])
        feature["id"] = properties["fips"]
        feature["properties"] = properties
        regions.append(properties)
    return regions


def build_regions(config: BuildConfig) -> dict[str, int]:
    """Build committed FR1 artifacts and return per-region counts."""

    if not config.geometry_script.exists():
        raise FileNotFoundError(
            f"Geometry helper not found at {config.geometry_script}"
        )

    source_paths = {source.key: _download(source, config.cache_dir) for source in SOURCES}
    config.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="colculator-regions-") as temporary_name:
        temporary = Path(temporary_name)
        state_dir = temporary / "states"
        county_dir = temporary / "counties"
        _safe_extract(source_paths["tiger_states"], state_dir)
        _safe_extract(source_paths["tiger_counties"], county_dir)

        raw_states = temporary / "states.geo.json"
        raw_counties = temporary / "counties.geo.json"
        _run_geometry_script(
            config.geometry_script,
            "shapefile-to-geojson",
            str(state_dir / "tl_2025_us_state.shp"),
            str(state_dir / "tl_2025_us_state.dbf"),
            str(raw_states),
            "GEOID,STATEFP,STUSPS,NAME",
        )
        _run_geometry_script(
            config.geometry_script,
            "shapefile-to-geojson",
            str(county_dir / "tl_2025_us_county.shp"),
            str(county_dir / "tl_2025_us_county.dbf"),
            str(raw_counties),
            "GEOID,STATEFP,NAME",
        )

        county_to_metro, metros = _metropolitan_membership(source_paths["omb_delineation"])
        state_collection = _load_feature_collection(raw_states)
        county_collection = _load_feature_collection(raw_counties)
        state_regions = _enrich_features(state_collection, _state_properties)
        county_regions = _enrich_features(
            county_collection,
            lambda properties: _county_properties(properties, county_to_metro),
        )

        enriched_states = temporary / "enriched-states.geo.json"
        enriched_counties = temporary / "enriched-counties.geo.json"
        _write_json(enriched_states, state_collection)
        _write_json(enriched_counties, county_collection)

        geometry_dir = config.output_dir / "geometry"
        geometry_dir.mkdir(parents=True, exist_ok=True)
        _run_geometry_script(
            config.geometry_script,
            "geojson-to-topojson",
            str(enriched_states),
            str(geometry_dir / "us-states.topo.json"),
            "states",
            str(TOPOJSON_QUANTIZATION),
            SIMPLIFICATION_PERCENT,
        )
        _run_geometry_script(
            config.geometry_script,
            "geojson-to-topojson",
            str(enriched_counties),
            str(geometry_dir / "us-counties.topo.json"),
            "counties",
            str(TOPOJSON_QUANTIZATION),
            SIMPLIFICATION_PERCENT,
        )

    regions = [*state_regions, *metros.values(), *county_regions]
    type_order = {"state": 0, "metro": 1, "county": 2}
    regions.sort(key=lambda region: (type_order[str(region["type"])], str(region["fips"])))
    _write_json(
        config.output_dir / "regions.json",
        {
            "schema_version": 1,
            "scope": "50 states and District of Columbia",
            "sources": {source.key: source.vintage for source in SOURCES},
            "regions": regions,
        },
    )
    _write_json(
        config.output_dir / "regions.sources.json",
        {
            "generated_from": [
                {
                    "key": source.key,
                    "publisher": source.publisher,
                    "vintage": source.vintage,
                    "url": source.url,
                    "sha256": source.sha256,
                }
                for source in SOURCES
            ],
            "transformation": {
                "tool": "shapefile + topojson-server + topojson-simplify",
                "simplification": SIMPLIFICATION_PERCENT,
                "quantization": TOPOJSON_QUANTIZATION,
                "scope_filter": "numeric state FIPS below 60 (50 states and District of Columbia)",
                "metro_membership": "Metropolitan Statistical Area rows only; micropolitan rows remain null",
            },
        },
        compact=False,
    )
    if config.seed_sql is not None:
        _write_region_seed(config.seed_sql, regions)
    return {
        "states": len(state_regions),
        "metros": len(metros),
        "counties": len(county_regions),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/regions"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("frontend/public/data"),
    )
    parser.add_argument(
        "--geometry-script",
        type=Path,
        default=Path("scripts/geometry.mjs"),
    )
    parser.add_argument(
        "--seed-sql",
        type=Path,
        default=Path("supabase/seed.sql"),
    )
    return parser.parse_args()


def main() -> None:
    arguments = _parse_args()
    counts = build_regions(
        BuildConfig(
            cache_dir=arguments.cache_dir,
            output_dir=arguments.output_dir,
            geometry_script=arguments.geometry_script,
            seed_sql=arguments.seed_sql,
        )
    )
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    main()
