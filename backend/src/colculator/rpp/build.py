"""Build FR2 state and metro RPP artifacts from the official BEA API."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable


BEA_API_URL = "https://apps.bea.gov/api/data/"
SOURCE = "official_bea"
TABLES = {"state": ("SARPP", "STATE"), "metro": ("MARPP", "MSA")}
COMPONENTS = {
    1: "rpp_all_items",
    2: "rpp_goods",
    3: "rpp_housing",
    4: "rpp_utilities",
    5: "rpp_other_services",
}
COMPONENT_LABELS = {
    1: "RPPs: All items",
    2: "RPPs: Goods",
    3: "RPPs: Services: Housing",
    4: "RPPs: Services: Utilities",
    5: "RPPs: Services: Other",
}
AGGREGATE_GEOFIPS = {"00000", "00999"}


@dataclass(frozen=True)
class BuildConfig:
    api_key: str
    regions_json: Path
    output_json: Path
    sources_json: Path
    seed_sql: Path | None = None
    year: int | None = None


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE entries without overriding the process environment."""

    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


class BEAClient:
    """Small BEA Regional API client that never logs or persists its API key."""

    def __init__(
        self,
        api_key: str,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        if not api_key.strip():
            raise ValueError("BEA_API_KEY is required")
        self._api_key = api_key.strip()
        self._opener = opener

    def _request(self, **parameters: str) -> dict[str, object]:
        query = urllib.parse.urlencode(
            {
                "UserID": self._api_key,
                "datasetname": "Regional",
                "ResultFormat": "JSON",
                **parameters,
            }
        )
        request = urllib.request.Request(
            f"{BEA_API_URL}?{query}",
            headers={"User-Agent": "Colculator RPP ingestion/0.1"},
        )
        try:
            with self._opener(request, timeout=120) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            retry_after = error.headers.get("Retry-After")
            suffix = f"; retry after {retry_after}s" if retry_after else ""
            raise RuntimeError(f"BEA API HTTP {error.code}{suffix}") from error

        results = payload.get("BEAAPI", {}).get("Results", {})
        if not isinstance(results, dict):
            raise ValueError("BEA API response did not include a Results object")
        error = results.get("Error")
        if isinstance(error, dict):
            code = error.get("APIErrorCode", "unknown")
            description = error.get("APIErrorDescription", "Unknown BEA API error")
            raise RuntimeError(f"BEA API error {code}: {description}")
        return results

    def available_years(self, table_name: str) -> set[int]:
        results = self._request(
            method="GetParameterValuesFiltered",
            TargetParameter="Year",
            TableName=table_name,
        )
        values = results.get("ParamValue")
        if not isinstance(values, list):
            raise ValueError(f"BEA did not return years for {table_name}")
        return {
            int(value["Key"])
            for value in values
            if isinstance(value, dict) and str(value.get("Key", "")).isdigit()
        }

    def data(
        self, table_name: str, geography: str, line_code: int, year: int
    ) -> list[dict[str, object]]:
        results = self._request(
            method="GetData",
            TableName=table_name,
            LineCode=str(line_code),
            Year=str(year),
            GeoFips=geography,
        )
        rows = results.get("Data")
        if not isinstance(rows, list):
            raise ValueError(
                f"BEA did not return data for {table_name} line {line_code}, {year}"
            )
        return [row for row in rows if isinstance(row, dict)]


def _decimal_value(raw: object) -> str | None:
    value = str(raw or "").strip().replace(",", "")
    if not value or value in {"(NA)", "(D)", "--"}:
        return None
    try:
        return format(Decimal(value), "f")
    except InvalidOperation as error:
        raise ValueError(f"Unexpected BEA numeric value: {raw!r}") from error


def _region_id(region_type: str, geo_fips: str) -> str:
    if region_type == "state":
        return f"US-STATE-{geo_fips[:2]}"
    return f"US-METRO-{geo_fips}"


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
        "year",
        "rpp_all_items",
        "rpp_goods",
        "rpp_housing",
        "rpp_utilities",
        "rpp_other_services",
        "source",
    )
    rows = [
        "(" + ",".join(_sql_literal(record[column]) for column in columns) + ")"
        for record in records
    ]
    updates = ",\n  ".join(
        f"{column} = excluded.{column}"
        for column in columns
        if column not in {"region_id", "year"}
    )
    sql = (
        "-- Generated by `npm run build:rpp`; do not edit by hand.\n"
        "begin;\n\n"
        f"insert into public.rpp_records ({', '.join(columns)})\nvalues\n  "
        + ",\n  ".join(rows)
        + "\non conflict (region_id, year) do update set\n  "
        + updates
        + ";\n\ncommit;\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql, encoding="utf-8")


def build_rpp(config: BuildConfig, client: BEAClient | None = None) -> dict[str, int]:
    """Fetch and validate the latest common state/metro BEA RPP vintage."""

    catalog = json.loads(config.regions_json.read_text(encoding="utf-8"))
    regions = catalog.get("regions")
    if not isinstance(regions, list):
        raise ValueError("Region catalog does not contain a regions list")
    valid_regions = {
        str(region["id"]): region
        for region in regions
        if isinstance(region, dict) and region.get("type") in TABLES
    }
    api = client or BEAClient(config.api_key)
    common_years = set.intersection(
        *(api.available_years(table_name) for table_name, _ in TABLES.values())
    )
    if not common_years:
        raise ValueError("SARPP and MARPP do not share an available year")
    year = config.year if config.year is not None else max(common_years)
    if year not in common_years:
        raise ValueError(f"{year} is not available in both SARPP and MARPP")

    records_by_id: dict[str, dict[str, object]] = {}
    counts: dict[str, int] = {}
    for region_type, (table_name, geography) in TABLES.items():
        seen_for_type: set[str] = set()
        for line_code, field in COMPONENTS.items():
            for row in api.data(table_name, geography, line_code, year):
                geo_fips = str(row.get("GeoFips", "")).strip()
                if geo_fips in AGGREGATE_GEOFIPS:
                    continue
                region_id = _region_id(region_type, geo_fips)
                region = valid_regions.get(region_id)
                if region is None:
                    raise ValueError(
                        f"BEA {table_name} geography {geo_fips} has no FR1 region"
                    )
                if str(row.get("TimePeriod")) != str(year):
                    raise ValueError(f"BEA returned the wrong year for {region_id}")
                record = records_by_id.setdefault(
                    region_id,
                    {
                        "region_id": region_id,
                        "year": year,
                        **{component: None for component in COMPONENTS.values()},
                        "source": SOURCE,
                    },
                )
                if record[field] is not None:
                    raise ValueError(f"Duplicate BEA value for {region_id} {field}")
                record[field] = _decimal_value(row.get("DataValue"))
                seen_for_type.add(region_id)
        counts[region_type] = len(seen_for_type)

    records = sorted(
        records_by_id.values(),
        key=lambda record: (
            str(valid_regions[str(record["region_id"])]["type"]),
            str(record["region_id"]),
        ),
    )
    _write_json(
        config.output_json,
        {
            "schema_version": 1,
            "year": year,
            "source": SOURCE,
            "records": records,
        },
        compact=True,
    )
    _write_json(
        config.sources_json,
        {
            "publisher": "U.S. Bureau of Economic Analysis",
            "dataset": "Regional",
            "year": year,
            "api_url": BEA_API_URL,
            "product_url": (
                "https://www.bea.gov/data/prices-inflation/"
                "regional-price-parities-state-and-metro-area"
            ),
            "download_archives": {
                "state": "https://apps.bea.gov/regional/zip/SARPP.zip",
                "metro": "https://apps.bea.gov/regional/zip/MARPP.zip",
            },
            "tables": {region_type: table for region_type, (table, _) in TABLES.items()},
            "components": {
                str(code): {
                    "field": COMPONENTS[code],
                    "bea_label": COMPONENT_LABELS[code],
                }
                for code in COMPONENTS
            },
            "source_tag": SOURCE,
            "notes": (
                "All five official BEA RPP series are preserved. The requirements' "
                "rpp_services shorthand is represented without loss as utilities and "
                "other services."
            ),
        },
        compact=False,
    )
    if config.seed_sql is not None:
        _write_seed(config.seed_sql, records)
    return {"year": year, "records": len(records), **counts}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--regions-json", type=Path, default=Path("frontend/public/data/regions.json")
    )
    parser.add_argument(
        "--output-json", type=Path, default=Path("frontend/public/data/rpp.json")
    )
    parser.add_argument(
        "--sources-json",
        type=Path,
        default=Path("frontend/public/data/rpp.sources.json"),
    )
    parser.add_argument(
        "--seed-sql", type=Path, default=Path("supabase/seeds/rpp.sql")
    )
    parser.add_argument("--year", type=int)
    return parser.parse_args()


def main() -> None:
    arguments = _parse_args()
    load_dotenv(arguments.env_file)
    api_key = os.environ.get("BEA_API_KEY", "")
    result = build_rpp(
        BuildConfig(
            api_key=api_key,
            regions_json=arguments.regions_json,
            output_json=arguments.output_json,
            sources_json=arguments.sources_json,
            seed_sql=arguments.seed_sql,
            year=arguments.year,
        )
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
