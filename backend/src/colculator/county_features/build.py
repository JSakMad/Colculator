"""Build source-tagged county features from Zillow, HUD, Census, and tax inputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import time
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
CENSUS_SUBDIVISION_GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2024_Gazetteer/2024_Gaz_cousubs_national.zip"
)
CENSUS_REDISTRICTING_BASE_URL = (
    "https://www2.census.gov/programs-surveys/decennial/2020/data/"
    "01-Redistricting_File--PL_94-171"
)
CENSUS_SUBDIVISION_ARCHIVES = {
    "09": ("Connecticut", "ct"),
    "23": ("Maine", "me"),
    "25": ("Massachusetts", "ma"),
    "33": ("New_Hampshire", "nh"),
    "44": ("Rhode_Island", "ri"),
}
HUD_API_URL = "https://www.huduser.gov/hudapi/public/fmr"
HUD_PRODUCT_URL = "https://www.huduser.gov/portal/datasets/fmr.html"
TAX_RATE_DEFINITION = (
    "Tax Foundation 2026 state income tax effective rate at $100,000 gross income "
    "for a single filer, and combined state plus population-weighted-average local "
    "sales tax rate. Both are applied uniformly to every county in the state."
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
    "state_income_tax_rate": "tax_foundation_2026",
    "local_sales_tax_rate": "tax_foundation_2026",
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


def parse_current_subdivision_counties(path: Path) -> dict[str, str]:
    """Map state + county-subdivision code to its current county equivalent."""

    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.endswith(".txt")]
        if len(members) != 1:
            raise ValueError("Census subdivision Gazetteer must contain one text file")
        text = io.TextIOWrapper(archive.open(members[0]), encoding="utf-8-sig")
        reader = csv.DictReader(text, delimiter="\t")
        values: dict[str, str] = {}
        for row in reader:
            cleaned = {key.strip(): value.strip() for key, value in row.items()}
            geoid = cleaned["GEOID"]
            if len(geoid) != 10 or not geoid.isdigit():
                continue
            if not geoid.startswith("09"):
                continue
            # Code 00000 is a county balance, not a named town/subdivision, and
            # is intentionally reused across counties.
            if geoid.endswith("00000"):
                continue
            key = geoid[:2] + geoid[5:]
            county_fips = geoid[:5]
            existing = values.setdefault(key, county_fips)
            if existing != county_fips:
                raise ValueError(
                    f"County-subdivision code {key} maps to multiple current counties"
                )
    return values


class HUDClient:
    """Minimal authenticated client for HUD's free FMR dataset API."""

    def __init__(
        self,
        token: str,
        opener: Callable[..., object] = urllib.request.urlopen,
        cache_dir: Path | None = None,
    ) -> None:
        if not token.strip():
            raise ValueError("HUD_API_TOKEN is required")
        self._token = token.strip()
        self._opener = opener
        self._cache_dir = cache_dir

    def _get(self, endpoint: str, *, year: int | None = None) -> object:
        cache_path: Path | None = None
        if self._cache_dir is not None:
            suffix = "latest" if year is None else str(year)
            cache_path = self._cache_dir / f"{endpoint.replace('/', '_')}_{suffix}.json"
            if cache_path.exists() and cache_path.stat().st_size:
                return json.loads(cache_path.read_text(encoding="utf-8"))
        suffix = "" if year is None else f"?year={year}"
        request = urllib.request.Request(
            f"{HUD_API_URL}/{endpoint}{suffix}",
            headers={
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "Colculator county feature ingestion/0.1",
            },
        )
        last_error: OSError | None = None
        for attempt in range(3):
            try:
                with self._opener(request, timeout=120) as response:
                    payload = json.load(response)
                break
            except OSError as error:
                last_error = error
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        else:  # pragma: no cover - loop either succeeds or raises.
            raise RuntimeError("HUD request failed") from last_error
        if isinstance(payload, dict) and str(payload.get("status", "")).startswith("4"):
            raise RuntimeError(f"HUD API error: {payload}")
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        return payload

    def county_fmrs(
        self,
        year: int,
        *,
        allowed_counties: set[str] | None = None,
        subdivision_population: dict[str, Decimal] | None = None,
        current_subdivision_county: dict[str, str] | None = None,
    ) -> dict[str, dict[str, str]]:
        """Fetch states and population-weight conflicting New England town FMRs."""

        states = _hud_data_list(self._get("listStates"))
        county_entities: dict[str, list[tuple[str, dict[str, str]]]] = {}
        conflicts: set[str] = set()
        for state in states:
            state_code = str(state.get("state_code", "")).strip()
            raw_state_fips = str(state.get("state_num", "")).strip()
            try:
                state_fips = str(int(Decimal(raw_state_fips))).zfill(2)
            except (InvalidOperation, ValueError):
                continue
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
                subdivision_key = entity_id[:2] + entity_id[5:]
                if (
                    current_subdivision_county
                    and subdivision_key in current_subdivision_county
                ):
                    county_fips = current_subdivision_county[subdivision_key]
                if allowed_counties is not None and county_fips not in allowed_counties:
                    continue
                record = {
                    "hud_fmr_studio": _required_hud_value(county, "Efficiency"),
                    "hud_fmr_1br": _required_hud_value(county, "One-Bedroom"),
                    "hud_fmr_2br": _required_hud_value(county, "Two-Bedroom"),
                    "hud_fmr_3br": _required_hud_value(county, "Three-Bedroom"),
                }
                county_entities.setdefault(county_fips, []).append((entity_id, record))

        values: dict[str, dict[str, str]] = {}
        for county_fips, entities in county_entities.items():
            unique_records = {tuple(sorted(record.items())) for _, record in entities}
            if len(unique_records) == 1:
                values[county_fips] = entities[0][1]
                continue
            if subdivision_population is None:
                conflicts.add(county_fips)
                continue
            missing = [
                entity_id
                for entity_id, _ in entities
                if entity_id not in subdivision_population
            ]
            if missing:
                raise ValueError(
                    f"Missing Census subdivision population for HUD {county_fips}: "
                    + ", ".join(sorted(missing))
                )
            total_population = sum(
                subdivision_population[entity_id] for entity_id, _ in entities
            )
            if total_population <= 0:
                raise ValueError(
                    f"HUD county {county_fips} has no populated Census subdivisions"
                )
            values[county_fips] = {
                field: format(
                    sum(
                        Decimal(record[field]) * subdivision_population[entity_id]
                        for entity_id, record in entities
                    )
                    / total_population,
                    ".6f",
                )
                for field in (
                    "hud_fmr_studio",
                    "hud_fmr_1br",
                    "hud_fmr_2br",
                    "hud_fmr_3br",
                )
            }
        if conflicts:
            raise ValueError(
                "HUD publishes conflicting town-level FMRs within these county FIPS; "
                "Census subdivision populations are required to aggregate: "
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


def parse_subdivision_population(path: Path, state_abbreviation: str) -> dict[str, Decimal]:
    """Read 2020 Census PL total population for summary-level 060 geographies."""

    prefix = state_abbreviation.lower()
    with zipfile.ZipFile(path) as archive:
        populations_by_logrec: dict[str, Decimal] = {}
        with archive.open(f"{prefix}000012020.pl") as raw_segment:
            segment = io.TextIOWrapper(raw_segment, encoding="ascii")
            for row in csv.reader(segment, delimiter="|"):
                if len(row) > 5:
                    populations_by_logrec[row[4]] = Decimal(row[5])

        values: dict[str, Decimal] = {}
        with archive.open(f"{prefix}geo2020.pl") as raw_geography:
            geography = io.TextIOWrapper(raw_geography, encoding="cp1252")
            for row in csv.reader(geography, delimiter="|"):
                if len(row) <= 8 or row[2] != "060":
                    continue
                entity_id = row[8].removeprefix("0600000US")
                population = populations_by_logrec.get(row[7])
                if len(entity_id) == 10 and population is not None:
                    values[entity_id] = population
    return values


def load_subdivision_population(cache_dir: Path) -> tuple[dict[str, Decimal], list[dict[str, str]]]:
    values: dict[str, Decimal] = {}
    sources: list[dict[str, str]] = []
    for state_fips, (directory, abbreviation) in CENSUS_SUBDIVISION_ARCHIVES.items():
        url = (
            f"{CENSUS_REDISTRICTING_BASE_URL}/{directory}/"
            f"{abbreviation}2020.pl.zip"
        )
        path = _download(url, cache_dir / f"census_pl_2020_{state_fips}.zip")
        state_values = parse_subdivision_population(path, abbreviation)
        if not state_values:
            raise ValueError(f"No Census county subdivisions found in {path}")
        values.update(state_values)
        sources.append({"url": url, "sha256": _sha256(path)})
    return values, sources


def parse_tax_rates(path: Path) -> tuple[dict[str, dict[str, str]], set[str]]:
    if not path.exists():
        raise ValueError(
            f"Generated tax file is required at {path}; run `npm run build:taxes`"
        )
    rates: dict[str, dict[str, str]] = {}
    urls: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "county_fips",
            "tax_year",
            "state_income_tax_rate",
            "local_sales_tax_rate",
            "state_income_tax_source_url",
            "local_sales_tax_source_url",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Tax CSV must contain {sorted(required)}")
        for row in reader:
            fips = row["county_fips"].strip().zfill(5)
            income_url = row["state_income_tax_source_url"].strip()
            sales_url = row["local_sales_tax_source_url"].strip()
            if (
                len(fips) != 5
                or not fips.isdigit()
                or not income_url.startswith("https://")
                or not sales_url.startswith("https://")
            ):
                raise ValueError(f"Invalid or unsourced tax row: {row}")
            rates[fips] = {
                "state_income_tax_rate": _required_rate(
                    row["state_income_tax_rate"], "state_income_tax_rate"
                ),
                "local_sales_tax_rate": _required_rate(
                    row["local_sales_tax_rate"], "local_sales_tax_rate"
                ),
                "tax_year": str(int(row["tax_year"])),
                "state_income_tax_source_url": income_url,
                "local_sales_tax_source_url": sales_url,
            }
            urls.update((income_url, sales_url))
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
    subdivision_geography_path = _download(
        CENSUS_SUBDIVISION_GAZETTEER_URL,
        config.cache_dir / "census_subdivision_gazetteer.zip",
    )
    zhvi = parse_zillow(zhvi_path, config.year, "zhvi")
    zori = parse_zillow(zori_path, config.year, "zori")
    population = parse_population(population_path, config.year)
    land_area = parse_land_area(land_path)
    current_subdivision_county = parse_current_subdivision_counties(
        subdivision_geography_path
    )
    taxes, tax_urls = parse_tax_rates(config.tax_csv)
    subdivision_population, subdivision_sources = load_subdivision_population(
        config.cache_dir
    )
    hud = (
        hud_client
        or HUDClient(config.hud_api_token, cache_dir=config.cache_dir / "hud")
    ).county_fmrs(
        config.year,
        allowed_counties=set(counties),
        subdivision_population=subdivision_population,
        current_subdivision_county=current_subdivision_county,
    )

    missing_required = {
        "hud": sorted(set(counties) - set(hud)),
        "population": sorted(set(counties) - set(population)),
        "land_area": sorted(set(counties) - set(land_area)),
        "tax": sorted(set(counties) - set(taxes)),
    }
    if any(missing_required.values()):
        details = {
            key: {"count": len(value), "sample": value[:20]}
            for key, value in missing_required.items()
            if value
        }
        raise ValueError(f"Required county feature coverage is incomplete: {details}")

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
                    "tax_year": int(taxes[fips]["tax_year"]),
                    "state_income_tax_source_url": taxes[fips][
                        "state_income_tax_source_url"
                    ],
                    "local_sales_tax_source_url": taxes[fips][
                        "local_sales_tax_source_url"
                    ],
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
                "new_england_county_aggregation": (
                    "Town-level FMRs are weighted by 2020 Census PL 94-171 county-"
                    "subdivision population when HUD publishes multiple values within "
                    "one FR1 county."
                ),
                "subdivision_population_sources": subdivision_sources,
                "current_subdivision_geography_url": (
                    CENSUS_SUBDIVISION_GAZETTEER_URL
                ),
                "current_subdivision_geography_sha256": _sha256(
                    subdivision_geography_path
                ),
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
                "income_locality_exclusion": (
                    "Local income taxes, including New York City and municipal taxes "
                    "in parts of Ohio and Pennsylvania, are not modeled in v1."
                ),
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
