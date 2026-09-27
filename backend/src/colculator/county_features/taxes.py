"""Build county-expanded 2026 tax features from Tax Foundation workbooks."""

from __future__ import annotations

import csv
import json
import re
import shutil
import urllib.request
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree


INCOME_PAGE_URL = (
    "https://taxfoundation.org/data/all/state/state-income-tax-rates-2026/"
)
INCOME_WORKBOOK_URL = (
    "https://taxfoundation.org/wp-content/uploads/2026/02/"
    "2026-State-Individual-Income-Tax-Rates-Brackets.xlsx"
)
SALES_PAGE_URL = "https://taxfoundation.org/data/all/state/sales-tax-rates/"
SALES_WORKBOOK_URL = (
    "https://taxfoundation.org/wp-content/uploads/2026/01/2026-Sales-Tax-Data.xlsx"
)
GROSS_INCOME = Decimal("100000")
NO_WAGE_INCOME_TAX = {
    "Alaska",
    "Florida",
    "Nevada",
    "New Hampshire",
    "South Dakota",
    "Tennessee",
    "Texas",
    "Washington",
    "Wyoming",
}

_MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_STATE_ALIASES = {
    "Ala.": "Alabama", "Alaska": "Alaska", "Ariz.": "Arizona",
    "Ark.": "Arkansas", "Calif.": "California", "Colo.": "Colorado",
    "Conn.": "Connecticut", "Del.": "Delaware", "Fla.": "Florida",
    "Ga.": "Georgia", "Hawaii": "Hawaii", "Idaho": "Idaho",
    "Ill.": "Illinois", "Ind.": "Indiana", "Iowa": "Iowa",
    "Kans.": "Kansas", "Ky.": "Kentucky", "La.": "Louisiana",
    "Maine": "Maine", "Md.": "Maryland", "Mass.": "Massachusetts",
    "Mich.": "Michigan", "Minn.": "Minnesota", "Miss.": "Mississippi",
    "Mo.": "Missouri", "Mont.": "Montana", "Nebr.": "Nebraska",
    "Nev.": "Nevada", "N.H.": "New Hampshire", "N.J.": "New Jersey",
    "N.M.": "New Mexico", "N.Y.": "New York", "N.C.": "North Carolina",
    "N.D.": "North Dakota", "Ohio": "Ohio", "Okla.": "Oklahoma",
    "Ore.": "Oregon", "Pa.": "Pennsylvania", "R.I.": "Rhode Island",
    "S.C.": "South Carolina", "S.D.": "South Dakota", "Tenn.": "Tennessee",
    "Tex.": "Texas", "Utah": "Utah", "Vt.": "Vermont",
    "Va.": "Virginia", "Wash.": "Washington", "W.Va.": "West Virginia",
    "Wis.": "Wisconsin", "Wyo.": "Wyoming", "D.C.": "District of Columbia",
}


def download_workbook(url: str, destination: Path) -> Path:
    if destination.exists() and destination.stat().st_size:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    request = urllib.request.Request(
        url, headers={"User-Agent": "Colculator tax ingestion/0.1"}
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


def _xlsx_rows(path: Path, sheet: str) -> list[dict[str, str]]:
    """Read cached XLSX values using only the Python standard library."""

    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(node.text or "" for node in item.iter(_MAIN_NS + "t"))
                for item in strings
            ]
        worksheet = ElementTree.fromstring(archive.read(sheet))
    rows: list[dict[str, str]] = []
    for row in worksheet.iter(_MAIN_NS + "row"):
        values: dict[str, str] = {}
        for cell in row:
            if cell.tag != _MAIN_NS + "c":
                continue
            match = re.match(r"[A-Z]+", cell.attrib["r"])
            value_node = cell.find(_MAIN_NS + "v")
            value = "" if value_node is None else value_node.text or ""
            if cell.attrib.get("t") == "s" and value:
                value = shared[int(value)]
            if match:
                values[match.group()] = value.strip().replace("\N{NO-BREAK SPACE}", "")
        rows.append(values)
    return rows


def _state_name(raw: str) -> str | None:
    label = re.sub(r"\s*\([^)]*\)\s*$", "", raw.strip())
    return _STATE_ALIASES.get(label)


def _amount_or_credit(raw: str) -> tuple[Decimal, Decimal]:
    normalized = raw.strip().lower().replace(",", "")
    if not normalized or normalized in {"n.a.", "n.a"}:
        return Decimal(0), Decimal(0)
    match = re.fullmatch(r"\$?([0-9.]+)( credit)?", normalized)
    if not match:
        raise ValueError(f"Unsupported Tax Foundation adjustment: {raw!r}")
    amount = Decimal(match.group(1))
    return (Decimal(0), amount) if match.group(2) else (amount, Decimal(0))


def _progressive_tax(
    taxable_income: Decimal, brackets: list[tuple[Decimal, Decimal]]
) -> Decimal:
    tax = Decimal(0)
    ordered = sorted(brackets)
    for index, (threshold, rate) in enumerate(ordered):
        if taxable_income <= threshold:
            continue
        upper = ordered[index + 1][0] if index + 1 < len(ordered) else taxable_income
        tax += (min(taxable_income, upper) - threshold) * rate
    return tax


def parse_income_rates(path: Path) -> dict[str, Decimal]:
    rows = _xlsx_rows(path, "xl/worksheets/sheet1.xml")
    states: dict[str, dict[str, object]] = {}
    current: str | None = None
    for row in rows[2:]:
        found = _state_name(row.get("A", ""))
        if found:
            current = found
            states[current] = {
                "brackets": [],
                "standard": row.get("H", ""),
                "exemption": row.get("J", ""),
            }
        if not current:
            continue
        try:
            rate = Decimal(row.get("B", ""))
            threshold = Decimal(row.get("D", ""))
        except InvalidOperation:
            continue
        brackets = states[current]["brackets"]
        assert isinstance(brackets, list)
        brackets.append((threshold, rate))

    rates: dict[str, Decimal] = {}
    for state, data in states.items():
        if state in NO_WAGE_INCOME_TAX:
            rates[state] = Decimal(0)
            continue
        deduction, standard_credit = _amount_or_credit(str(data["standard"]))
        exemption, exemption_credit = _amount_or_credit(str(data["exemption"]))
        taxable = max(Decimal(0), GROSS_INCOME - deduction - exemption)
        brackets = data["brackets"]
        assert isinstance(brackets, list)
        tax = _progressive_tax(taxable, brackets)
        tax = max(Decimal(0), tax - standard_credit - exemption_credit)
        rates[state] = tax / GROSS_INCOME
    return rates


def parse_sales_rates(path: Path) -> dict[str, Decimal]:
    rates: dict[str, Decimal] = {}
    for row in _xlsx_rows(path, "xl/worksheets/sheet1.xml"):
        state = re.sub(r"\s*\([^)]*\)\s*$", "", row.get("A", "").strip())
        if state == "State" or not state:
            continue
        try:
            rates[state] = Decimal(row["F"])
        except (KeyError, InvalidOperation):
            continue
    return rates


def build_county_tax_rates(
    *, regions_json: Path, income_workbook: Path, sales_workbook: Path,
    output_csv: Path, tax_year: int = 2026,
) -> dict[str, int]:
    catalog = json.loads(regions_json.read_text(encoding="utf-8"))
    states = {
        region["id"]: region["name"]
        for region in catalog["regions"] if region.get("type") == "state"
    }
    counties = [
        region for region in catalog["regions"] if region.get("type") == "county"
    ]
    income = parse_income_rates(income_workbook)
    sales = parse_sales_rates(sales_workbook)
    expected = set(states.values())
    if set(income) != expected or set(sales) != expected:
        raise ValueError(
            "Tax Foundation state coverage does not match FR1 catalog: "
            f"income missing={sorted(expected - set(income))}, "
            f"income extra={sorted(set(income) - expected)}, "
            f"sales missing={sorted(expected - set(sales))}, "
            f"sales extra={sorted(set(sales) - expected)}"
        )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "county_fips", "tax_year", "state_income_tax_rate",
        "local_sales_tax_rate", "state_income_tax_source_url",
        "local_sales_tax_source_url",
    )
    with output_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for county in sorted(counties, key=lambda value: value["fips"]):
            state = states[county["parent_region_id"]]
            writer.writerow({
                "county_fips": county["fips"],
                "tax_year": tax_year,
                "state_income_tax_rate": format(income[state], "f"),
                "local_sales_tax_rate": format(sales[state], "f"),
                "state_income_tax_source_url": INCOME_PAGE_URL,
                "local_sales_tax_source_url": SALES_PAGE_URL,
            })
    return {"tax_year": tax_year, "states": len(expected), "counties": len(counties)}
