#!/usr/bin/env python3
"""Generate state-level tax features expanded to each FR1 county."""

import argparse
import json
from pathlib import Path

from colculator.county_features.taxes import (
    INCOME_WORKBOOK_URL, SALES_WORKBOOK_URL, build_county_tax_rates,
    build_state_income_tax_rules,
    download_workbook,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tax-year", type=int, default=2026)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/county_features"))
    parser.add_argument("--output", type=Path, default=Path("data/manual/county_tax_rates.csv"))
    parser.add_argument(
        "--rules-output",
        type=Path,
        default=Path("frontend/public/data/state_income_tax_rules.json"),
    )
    args = parser.parse_args()
    income = download_workbook(
        INCOME_WORKBOOK_URL, args.cache_dir / f"tax_foundation_income_{args.tax_year}.xlsx"
    )
    sales = download_workbook(
        SALES_WORKBOOK_URL, args.cache_dir / f"tax_foundation_sales_{args.tax_year}.xlsx"
    )
    result = build_county_tax_rates(
        regions_json=Path("frontend/public/data/regions.json"),
        income_workbook=income,
        sales_workbook=sales,
        output_csv=args.output,
        tax_year=args.tax_year,
    )
    rules_result = build_state_income_tax_rules(
        regions_json=Path("frontend/public/data/regions.json"),
        income_workbook=income,
        output_json=args.rules_output,
        tax_year=args.tax_year,
    )
    result.update({"rule_states": rules_result["states"]})
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
