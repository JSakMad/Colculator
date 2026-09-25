"""Build source-tagged county features from Zillow, HUD, Census, and tax inputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable

from colculator.rpp.build import load_dotenv


ZILLOW_ZHVI_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zhvi/"
    "County_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
)
ZILLOW_ZORI_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zori/"
    "County_zori_uc_sfrcondomfr_sm_month.csv"
)
CENSUS_POPULATION_URL = (
    "https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/"
    "counties/totals/co-est2024-alldata.csv"
)
CENSUS_GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2024_Gazetteer/2024_Gaz_counties_national.zip"
)
HUD_API_URL = "https://www.huduser.gov/hudapi/public/fmr"
HUD_PRODUCT_URL = "https://www.huduser.gov/portal/datasets/fmr.html"
TAX_RATE_DEFINITION = (
    "User-supplied official-source rates. Missing or unsourced values are rejected."
)

FEATURE_FIELDS = (
    "zhvi",
    "zori",
    "hud_fmr_studio",
    "hud_fmr_1br",
    "hud_fmr_2br",
    "hud_fmr_3br",
    "state_income_tax_rate",
    "local_sales_tax_rate",
    "population_density",
)
SOURCE_TAGS = {
    "zhvi": "zillow_research",
    "zori": "zillow_research",
    "hud_fmr_studio": "hud_fmr",
    "hud_fmr_1br": "hud_fmr",
    "hud_fmr_2br": "hud_fmr",
    "hud_fmr_3br": "hud_fmr",
    "state_income_tax_rate": "official_tax_source",
    "local_sales_tax_rate": "official_tax_source",
    "population_density": "census_population_estimates_gazetteer",
}


@dataclass(frozen=True)
class BuildConfig:
    year: int
    regions_json: Path
    tax_csv: Path
    cache_dir: Path
    output_json: Path
    sources_json: Path
    seed_sql: Path | None = None
    hud_api_token: str = ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> Path:
    if destination.exists() and destination.stat().st_size:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    request = urllib.request.Request(
        url, headers={"User-Agent": "Colculator county feature ingestion/0.1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
        if not temporary.stat().st_size:
            raise ValueError(f"Source returned an empty file: {url}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _decimal(raw: object, *, field: str) -> str | None:
    value = str(raw or "").strip().replace(",", "")
    if not value:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"Invalid {field} value: {raw!r}") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"Invalid {field} value: {raw!r}")
    return format(parsed, "f")


def _county_fips(row: dict[str, str]) -> str:
    state = row.get("StateCodeFIPS", "").strip().zfill(2)
    county = row.get("MunicipalCodeFIPS", "").strip().zfill(3)
    fips = state + county
    if len(fips) != 5 or not fips.isdigit():
        raise ValueError(f"Zillow row has invalid county FIPS fields: {row}")
    return fips


def parse_zillow(path: Path, year: int, field: str) -> dict[str, str | None]:
    """Return the December observation for a Zillow county index."""

    month = f"{year}-12-31"
    values: dict[str, str | None] = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or month not in reader.fieldnames:
            raise ValueError(f"Zillow {field} file has no {month} column")
        for row in reader:
            if row.get("RegionType", "").strip().lower() != "county":
                continue
            fips = _county_fips(row)
            if fips in values:
                raise ValueError(f"Duplicate Zillow county {fips} in {path}")
            values[fips] = _decimal(row.get(month), field=field)
    return values


def parse_population(path: Path, year: int) -> dict[str, Decimal]:
    field = f"POPESTIMATE{year}"
    values: dict[str, Decimal] = {}
    # Census Population Estimates files are published as Windows-1252 CSVs.
    with path.open(encoding="cp1252", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or field not in reader.fieldnames:
            raise ValueError(f"Census population file has no {field} column")
        for row in reader:
            if row.get("SUMLEV") != "050":
                continue
            fips = row["STATE"].zfill(2) + row["COUNTY"].zfill(3)
            population = Decimal(row[field])
            if population < 0:
                raise ValueError(f"Negative Census population for {fips}")
            values[fips] = population
    return values


def parse_land_area(path: Path) -> dict[str, Decimal]:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.endswith(".txt")]
        if len(members) != 1:
            raise ValueError("Census Gazetteer archive must contain one text file")
        text = io.TextIOWrapper(archive.open(members[0]), encoding="utf-8-sig")
        reader = csv.DictReader(text, delimiter="\t")
        values: dict[str, Decimal] = {}
        for row in reader:
            cleaned = {key.strip(): value.strip() for key, value in row.items()}
            fips = cleaned["GEOID"].zfill(5)
            area = Decimal(cleaned["ALAND_SQMI"])
            if area <= 0:
                raise ValueError(f"Non-positive Census land area for {fips}")
            values[fips] = area
    return values


class HUDClient:
    """Minimal authenticated client for HUD's free FMR dataset API."""

    def __init__(
        self,
        token: str,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        if not token.strip():
            raise ValueError("HUD_API_TOKEN is required")
        self._token = token.strip()
        self._opener = opener

    def _get(self, endpoint: str, *, year: int | None = None) -> object:
        suffix = "" if year is None else f"?year={year}"
        request = urllib.request.Request(
            f"{HUD_API_URL}/{endpoint}{suffix}",
            headers={
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "Colculator county feature ingestion/0.1",
            },
        )
        with self._opener(request, timeout=120) as response:
            payload = json.load(response)
        if isinstance(payload, dict) and str(payload.get("status", "")).startswith("4"):
            raise RuntimeError(f"HUD API error: {payload}")
        return payload

    def county_fmrs(
        self, year: int, *, allowed_counties: set[str] | None = None
    ) -> dict[str, dict[str, str]]:
        """Fetch one state at a time and reject ambiguous town-level duplicates."""

        states = _hud_data_list(self._get("listStates"))
        values: dict[str, dict[str, str]] = {}
        conflicts: set[str] = set()
        for state in states:
            state_code = str(state.get("state_code", "")).strip()
            state_fips = str(state.get("state_num", "")).strip().zfill(2)
            if allowed_counties is not None and not any(
                fips.startswith(state_fips) for fips in allowed_counties
            ):
                continue
            if not state_code:
                continue
            payload = self._get(f"statedata/{state_code}", year=year)
            data = payload.get("data") if isinstance(payload, dict) else None
            counties = data.get("counties") if isinstance(data, dict) else None
            if not isinstance(counties, list):
                raise ValueError(f"Unexpected HUD state response for {state_code}")
            for county in counties:
                if not isinstance(county, dict):
                    continue
                entity_id = str(county.get("fips_code", "")).strip()
                county_fips = entity_id[:5]
                if len(county_fips) != 5 or not county_fips.isdigit():
                    continue
                if allowed_counties is not None and county_fips not in allowed_counties:
                    continue
                record = {
                    "hud_fmr_studio": _required_hud_value(county, "Efficiency"),
                    "hud_fmr_1br": _required_hud_value(county, "One-Bedroom"),
                    "hud_fmr_2br": _required_hud_value(county, "Two-Bedroom"),
                    "hud_fmr_3br": _required_hud_value(county, "Three-Bedroom"),
                }
                existing = values.setdefault(county_fips, record)
                if existing != record:
                    conflicts.add(county_fips)
        if conflicts:
            raise ValueError(
                "HUD publishes conflicting town-level FMRs within these county FIPS; "
                "an approved aggregation rule is required: "
                + ", ".join(sorted(conflicts))
            )
        return values


def _hud_data_list(payload: object) -> list[dict[str, object]]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        raise ValueError(f"Unexpected HUD list response: {payload!r}")
    return [row for row in data if isinstance(row, dict)]


def _required_hud_value(data: dict[str, object], name: str) -> str:
    value = _decimal(data.get(name), field=f"HUD {name}")
    if value is None:
        raise ValueError(f"HUD response is missing {name}: {data}")
    return value


def parse_tax_rates(path: Path, year: int) -> tuple[dict[str, dict[str, str]], set[str]]:
    if not path.exists():
        raise ValueError(
            f"Official-source tax file is required at {path}; see the committed template"
        )
    rates: dict[str, dict[str, str]] = {}
    urls: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "county_fips",
            "year",
            "state_income_tax_rate",
            "local_sales_tax_rate",
            "source_url",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Tax CSV must contain {sorted(required)}")
        for row in reader:
            if int(row["year"]) != year:
                continue
            fips = row["county_fips"].strip().zfill(5)
            source_url = row["source_url"].strip()
            if len(fips) != 5 or not fips.isdigit() or not source_url.startswith("https://"):
                raise ValueError(f"Invalid or unsourced tax row: {row}")
            rates[fips] = {
                "state_income_tax_rate": _required_rate(
                    row["state_income_tax_rate"], "state_income_tax_rate"
                ),
                "local_sales_tax_rate": _required_rate(
                    row["local_sales_tax_rate"], "local_sales_tax_rate"
                ),
                "source_url": source_url,
            }
            urls.add(source_url)
    return rates, urls


def _required_decimal(raw: object, field: str) -> str:
    value = _decimal(raw, field=field)
    if value is None:
        raise ValueError(f"Missing required {field}")
    return value


def _required_rate(raw: object, field: str) -> str:
    value = _required_decimal(raw, field)
    if Decimal(value) > 1:
        raise ValueError(f"{field} must be a decimal proportion between 0 and 1")
    return value


def _write_json(path: Path, payload: object, *, compact: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(
            payload,
            stream,
            ensure_ascii=False,
            separators=(",", ":") if compact else None,
            indent=None if compact else 2,
        )
        if not compact:
            stream.write("\n")


def _sql(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, dict):
        value = json.dumps(value, separators=(",", ":"), sort_keys=True)
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _write_seed(path: Path, records: list[dict[str, object]]) -> None:
    columns = ("county_fips", "year", *FEATURE_FIELDS, "source_metadata")
    rows = [
        "(" + ",".join(_sql(record[column]) for column in columns) + ")"
        for record in records
    ]
    updates = ",\n  ".join(
        f"{column} = excluded.{column}" for column in (*FEATURE_FIELDS, "source_metadata")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "-- Generated by `npm run build:county-features`; do not edit by hand.\n"
        "begin;\n\n"
        f"insert into public.county_features ({', '.join(columns)})\nvalues\n  "
        + ",\n  ".join(rows)
        + "\non conflict (county_fips, year) do update set\n  "
        + updates
        + ";\n\ncommit;\n",
        encoding="utf-8",
    )


def build_county_features(
    config: BuildConfig, *, hud_client: HUDClient | None = None
) -> dict[str, int]:
    catalog = json.loads(config.regions_json.read_text(encoding="utf-8"))
    counties = {
        str(region["fips"]): region
        for region in catalog["regions"]
        if region.get("type") == "county"
    }
    zhvi_path = _download(ZILLOW_ZHVI_URL, config.cache_dir / "zillow_zhvi.csv")
    zori_path = _download(ZILLOW_ZORI_URL, config.cache_dir / "zillow_zori.csv")
    population_path = _download(
        CENSUS_POPULATION_URL, config.cache_dir / "census_population.csv"
    )
    land_path = _download(
        CENSUS_GAZETTEER_URL, config.cache_dir / "census_gazetteer.zip"
    )
    zhvi = parse_zillow(zhvi_path, config.year, "zhvi")
    zori = parse_zillow(zori_path, config.year, "zori")
    population = parse_population(population_path, config.year)
    land_area = parse_land_area(land_path)
    taxes, tax_urls = parse_tax_rates(config.tax_csv, config.year)
    hud = (hud_client or HUDClient(config.hud_api_token)).county_fmrs(
        config.year, allowed_counties=set(counties)
    )

    missing_required = {
        "hud": sorted(set(counties) - set(hud)),
        "population": sorted(set(counties) - set(population)),
        "land_area": sorted(set(counties) - set(land_area)),
        "tax": sorted(set(counties) - set(taxes)),
    }
    if any(missing_required.values()):
        counts = {key: len(value) for key, value in missing_required.items() if value}
        raise ValueError(f"Required county feature coverage is incomplete: {counts}")

    records: list[dict[str, object]] = []
    for fips in sorted(counties):
        density = population[fips] / land_area[fips]
        records.append(
            {
                "county_fips": fips,
                "year": config.year,
                "zhvi": zhvi.get(fips),
                "zori": zori.get(fips),
                **hud[fips],
                "state_income_tax_rate": taxes[fips]["state_income_tax_rate"],
                "local_sales_tax_rate": taxes[fips]["local_sales_tax_rate"],
                "population_density": format(density, ".6f"),
                # Retained only to aggregate county inputs into official state/metro
                # training-label geographies. It is not a model feature.
                "population_weight": str(population[fips]),
                "source_metadata": {
                    "field_source_tags": SOURCE_TAGS,
                    "zillow_observation": f"{config.year}-12-31",
                    "hud_fiscal_year": config.year,
                    "census_population_year": config.year,
                    "tax_source_url": taxes[fips]["source_url"],
                },
            }
        )

    _write_json(
        config.output_json,
        {"schema_version": 1, "year": config.year, "records": records},
        compact=True,
    )
    _write_json(
        config.sources_json,
        {
            "year": config.year,
            "fields": SOURCE_TAGS,
            "zillow": {
                "publisher": "Zillow Research",
                "zhvi_url": ZILLOW_ZHVI_URL,
                "zori_url": ZILLOW_ZORI_URL,
                "zhvi_sha256": _sha256(zhvi_path),
                "zori_sha256": _sha256(zori_path),
                "observation": f"{config.year}-12-31",
                "attribution_required": True,
            },
            "hud": {
                "publisher": "U.S. Department of Housing and Urban Development",
                "api_url": HUD_API_URL,
                "product_url": HUD_PRODUCT_URL,
                "fiscal_year": config.year,
                "authentication": "free HUD USER dataset API bearer token",
            },
            "census": {
                "publisher": "U.S. Census Bureau",
                "population_url": CENSUS_POPULATION_URL,
                "gazetteer_url": CENSUS_GAZETTEER_URL,
                "population_sha256": _sha256(population_path),
                "gazetteer_sha256": _sha256(land_path),
                "density_formula": "POPESTIMATE2024 / ALAND_SQMI",
            },
            "tax": {
                "definition": TAX_RATE_DEFINITION,
                "source_urls": sorted(tax_urls),
            },
            "missing_values": {
                "zhvi": sum(record["zhvi"] is None for record in records),
                "zori": sum(record["zori"] is None for record in records),
                "policy": "Unavailable Zillow observations remain null; no values are invented.",
            },
            "training_metadata": {
                "population_weight": (
                    "Census POPESTIMATE2024; retained for geographic aggregation only "
                    "and excluded from model features."
                )
            },
        },
        compact=False,
    )
    if config.seed_sql is not None:
        _write_seed(config.seed_sql, records)
    return {
        "year": config.year,
        "records": len(records),
        "missing_zhvi": sum(record["zhvi"] is None for record in records),
        "missing_zori": sum(record["zori"] is None for record in records),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--tax-csv", type=Path, default=Path("data/manual/county_tax_rates.csv")
    )
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/county_features"))
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    load_dotenv(args.env_file)
    config = BuildConfig(
        year=args.year,
        regions_json=Path("frontend/public/data/regions.json"),
        tax_csv=args.tax_csv,
        cache_dir=args.cache_dir,
        output_json=Path("frontend/public/data/county_features.json"),
        sources_json=Path("frontend/public/data/county_features.sources.json"),
        seed_sql=Path("supabase/seeds/county_features.sql"),
        hud_api_token=os.environ.get("HUD_API_TOKEN", ""),
    )
    print(json.dumps(build_county_features(config), sort_keys=True))


if __name__ == "__main__":
    main()
