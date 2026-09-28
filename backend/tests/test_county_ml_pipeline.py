import csv
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import numpy as np

from colculator.county_features.build import (
    FEATURE_FIELDS,
    HUDClient,
    parse_tax_rates,
    parse_zillow,
)
from colculator.county_features.taxes import _progressive_tax
from colculator.county_rpp.train import (
    MODEL_FEATURES,
    TrainConfig,
    predict_nonmetro,
    train_county_rpp,
)


ROOT = Path(__file__).resolve().parents[2]


class RecordingModel:
    def __init__(self, value: float) -> None:
        self.value = value
        self.rows_seen = 0

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        self.rows_seen += len(matrix)
        return np.full(len(matrix), self.value)


def feature(fips: str, base: int) -> dict[str, object]:
    record: dict[str, object] = {
        "county_fips": fips,
        "year": 2024,
        "population_weight": str(1000 + base),
    }
    for index, field in enumerate(MODEL_FEATURES, start=1):
        record[field] = str(base * index + index)
    return record


class CountyFeatureIngestionTest(unittest.TestCase):
    def test_model_features_match_spec_and_exclude_local_wages(self) -> None:
        self.assertEqual(FEATURE_FIELDS, MODEL_FEATURES)
        self.assertNotIn("local_wage", MODEL_FEATURES)
        self.assertNotIn("median_wage", MODEL_FEATURES)
        self.assertNotIn("population_weight", MODEL_FEATURES)

    def test_zillow_missing_value_remains_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "zillow.csv"
            path.write_text(
                "RegionType,StateCodeFIPS,MunicipalCodeFIPS,2024-12-31\n"
                "county,06,001,\n",
                encoding="utf-8",
            )
            self.assertEqual({"06001": None}, parse_zillow(path, 2024, "zhvi"))

    def test_tax_rows_must_be_complete_and_source_tagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tax.csv"
            path.write_text(
                "county_fips,tax_year,state_income_tax_rate,local_sales_tax_rate,"
                "state_income_tax_source_url,local_sales_tax_source_url\n"
                "06001,2026,0.093,0.0125,,https://example.com/sales\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Invalid or unsourced"):
                parse_tax_rates(path)

    def test_income_tax_brackets_are_applied_sequentially(self) -> None:
        tax = _progressive_tax(
            Decimal("100000"),
            [(Decimal("0"), Decimal("0.02")), (Decimal("50000"), Decimal("0.04"))],
        )
        self.assertEqual(Decimal("3000.00"), tax)

    def test_generated_tax_rates_cover_every_county_uniformly_by_state(self) -> None:
        tax_path = ROOT / "data" / "manual" / "county_tax_rates.csv"
        with tax_path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        catalog = json.loads(
            (ROOT / "frontend" / "public" / "data" / "regions.json").read_text()
        )
        counties = [
            region for region in catalog["regions"] if region.get("type") == "county"
        ]
        self.assertEqual(len(counties), len(rows))
        state_values: dict[str, set[tuple[str, str]]] = {}
        for row in rows:
            state_values.setdefault(row["county_fips"][:2], set()).add(
                (row["state_income_tax_rate"], row["local_sales_tax_rate"])
            )
            self.assertTrue(row["state_income_tax_source_url"].startswith("https://"))
            self.assertTrue(row["local_sales_tax_source_url"].startswith("https://"))
        self.assertTrue(all(len(values) == 1 for values in state_values.values()))
        for state_fips in ("02", "12", "32", "33", "46", "47", "48", "53", "56"):
            self.assertEqual("0", next(iter(state_values[state_fips]))[0])

    def test_hud_town_level_conflicts_are_never_silently_aggregated(self) -> None:
        payloads = {
            "listStates": {
                "data": [{"state_code": "MA", "state_num": "25.0"}]
            },
            "statedata/MA": {
                "data": {
                    "counties": [
                        {
                            "fips_code": "2502300010",
                            "Efficiency": 1000,
                            "One-Bedroom": 1100,
                            "Two-Bedroom": 1200,
                            "Three-Bedroom": 1300,
                        },
                        {
                            "fips_code": "2502300020",
                            "Efficiency": 1001,
                            "One-Bedroom": 1100,
                            "Two-Bedroom": 1200,
                            "Three-Bedroom": 1300,
                        },
                    ]
                }
            },
        }

        def opener(request, timeout):
            endpoint = request.full_url.split("/fmr/", 1)[1].split("?", 1)[0]
            return io.BytesIO(json.dumps(payloads[endpoint]).encode())

        with self.assertRaisesRegex(ValueError, "25023"):
            HUDClient("fixture-token", opener=opener).county_fmrs(
                2024, allowed_counties={"25023"}
            )

    def test_hud_town_level_conflicts_use_census_population_weights(self) -> None:
        payloads = {
            "listStates": {
                "data": [{"state_code": "MA", "state_num": "25.0"}]
            },
            "statedata/MA": {
                "data": {
                    "counties": [
                        {
                            "fips_code": "2502300010",
                            "Efficiency": 1000,
                            "One-Bedroom": 1100,
                            "Two-Bedroom": 1200,
                            "Three-Bedroom": 1300,
                        },
                        {
                            "fips_code": "2502300020",
                            "Efficiency": 2000,
                            "One-Bedroom": 2100,
                            "Two-Bedroom": 2200,
                            "Three-Bedroom": 2300,
                        },
                    ]
                }
            },
        }

        def opener(request, timeout):
            endpoint = request.full_url.split("/fmr/", 1)[1].split("?", 1)[0]
            return io.BytesIO(json.dumps(payloads[endpoint]).encode())

        values = HUDClient("fixture-token", opener=opener).county_fmrs(
            2024,
            allowed_counties={"25023"},
            subdivision_population={
                "2502300010": Decimal(100),
                "2502300020": Decimal(300),
            },
        )
        self.assertEqual("1750.000000", values["25023"]["hud_fmr_studio"])
        self.assertEqual("1950.000000", values["25023"]["hud_fmr_2br"])


class CountyEstimatorAcceptanceTest(unittest.TestCase):
    def test_generated_estimates_cover_only_nonmetro_counties(self) -> None:
        regions = json.loads(
            (ROOT / "frontend" / "public" / "data" / "regions.json").read_text()
        )["regions"]
        estimates = json.loads(
            (
                ROOT
                / "frontend"
                / "public"
                / "data"
                / "county_rpp_estimates.json"
            ).read_text()
        )["records"]
        nonmetro = {
            str(region["fips"])
            for region in regions
            if region.get("type") == "county" and region.get("msa_id") is None
        }
        self.assertEqual(nonmetro, {row["county_fips"] for row in estimates})
        for estimate in estimates:
            self.assertEqual("modeled", estimate["source"])
            self.assertEqual(0.95, estimate["confidence_interval"]["level"])

        metrics = json.loads(
            (
                ROOT
                / "frontend"
                / "public"
                / "data"
                / "county_rpp_model.metrics.json"
            ).read_text()
        )
        self.assertGreater(
            metrics["commerce_experimental_comparison"]["overlap"], 0
        )
        self.assertEqual(
            {"all_items", "housing"},
            set(metrics["cross_validation"]["targets"]),
        )

    def test_covered_metro_county_is_never_passed_to_a_model(self) -> None:
        regions = [
            {"type": "county", "fips": "01001", "msa_id": "US-METRO-10001"},
            {"type": "county", "fips": "01003", "msa_id": None},
        ]
        features = [feature("01001", 1), feature("01003", 2)]
        all_items = RecordingModel(91.0)
        housing = RecordingModel(82.0)
        estimates = predict_nonmetro(
            regions,
            features,
            {"all_items": all_items, "housing": housing},
            {"all_items": 3.0, "housing": 4.0},
            year=2024,
            model_version="fixture-v1",
        )
        self.assertEqual(["01003"], [row["county_fips"] for row in estimates])
        self.assertEqual(1, all_items.rows_seen)
        self.assertEqual(1, housing.rows_seen)
        self.assertEqual("modeled", estimates[0]["source"])
        self.assertIn("confidence_interval", estimates[0])

    def test_every_retrain_logs_cv_rmse_and_every_estimate_has_intervals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regions: list[dict[str, object]] = []
            features: list[dict[str, object]] = []
            rpp: list[dict[str, object]] = []
            for number in range(1, 13):
                state_fips = str(number).zfill(2)
                county_fips = state_fips + "001"
                state_id = f"US-STATE-{state_fips}"
                regions.extend(
                    [
                        {"id": state_id, "type": "state", "fips": state_fips},
                        {
                            "id": f"US-COUNTY-{county_fips}",
                            "type": "county",
                            "fips": county_fips,
                            "parent_region_id": state_id,
                            "msa_id": None,
                        },
                    ]
                )
                features.append(feature(county_fips, number))
                rpp.append(
                    {
                        "region_id": state_id,
                        "year": 2024,
                        "rpp_all_items": str(80 + number),
                        "rpp_housing": str(70 + number * 2),
                        "source": "official_bea",
                    }
                )

            paths = {
                name: root / name
                for name in (
                    "regions.json",
                    "rpp.json",
                    "features.json",
                    "estimates.json",
                    "metrics.json",
                    "seed.sql",
                    "commerce.csv",
                )
            }
            paths["regions.json"].write_text(
                json.dumps({"regions": regions}), encoding="utf-8"
            )
            paths["rpp.json"].write_text(
                json.dumps({"year": 2024, "records": rpp}), encoding="utf-8"
            )
            paths["features.json"].write_text(
                json.dumps({"year": 2024, "records": features}), encoding="utf-8"
            )
            with paths["commerce.csv"].open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=("county_fips", "rpp_all_items")
                )
                writer.writeheader()
                writer.writerow({"county_fips": "01001", "rpp_all_items": "81"})

            metrics = train_county_rpp(
                TrainConfig(
                    year=2024,
                    regions_json=paths["regions.json"],
                    rpp_json=paths["rpp.json"],
                    features_json=paths["features.json"],
                    output_json=paths["estimates.json"],
                    metrics_json=paths["metrics.json"],
                    seed_sql=paths["seed.sql"],
                    commerce_csv=paths["commerce.csv"],
                )
            )
            for target in ("all_items", "housing"):
                self.assertGreaterEqual(
                    metrics["cross_validation"]["targets"][target]["cv_rmse"], 0
                )
            estimates = json.loads(paths["estimates.json"].read_text())["records"]
            self.assertEqual(12, len(estimates))
            for estimate in estimates:
                self.assertEqual("modeled", estimate["source"])
                interval = estimate["confidence_interval"]
                self.assertEqual(0.95, interval["level"])
                self.assertIn("all_items", interval)
                self.assertIn("housing", interval)
            logged = json.loads(paths["metrics.json"].read_text())
            self.assertEqual(metrics, logged)
            self.assertEqual(
                "research_estimate_not_verified_truth",
                logged["commerce_experimental_comparison"]["reference_kind"],
            )

    def test_database_rejects_modeled_rows_for_metro_counties(self) -> None:
        migration = next(
            (ROOT / "supabase" / "migrations").glob(
                "*_create_county_features_and_rpp_estimates.sql"
            )
        )
        sql = migration.read_text(encoding="utf-8").lower()
        self.assertIn("create table public.county_features", sql)
        self.assertIn("create table public.county_rpp_estimates", sql)
        self.assertIn("enforce_nonmetro_county_estimate", sql)
        self.assertIn("and msa_id is null", sql)
        self.assertIn("source = 'modeled'", sql)
        self.assertIn("enable row level security", sql)
        self.assertNotIn("grant insert on table public.county_rpp_estimates to anon", sql)


if __name__ == "__main__":
    unittest.main()
