import json
import unittest
from pathlib import Path

from colculator.rpp.build import COMPONENTS, SOURCE, _decimal_value


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "frontend" / "public" / "data"


class OfficialRPPAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads((DATA_DIR / "rpp.json").read_text(encoding="utf-8"))
        cls.records = cls.catalog["records"]
        cls.by_region = {record["region_id"]: record for record in cls.records}
        region_catalog = json.loads(
            (DATA_DIR / "regions.json").read_text(encoding="utf-8")
        )
        cls.regions = {region["id"]: region for region in region_catalog["regions"]}

    def test_every_record_is_an_official_state_or_metro_value(self) -> None:
        self.assertEqual(2024, self.catalog["year"])
        self.assertEqual(SOURCE, self.catalog["source"])
        self.assertEqual(len(self.records), len(self.by_region))
        self.assertEqual(438, len(self.records))
        self.assertEqual(
            51,
            sum(
                self.regions[record["region_id"]]["type"] == "state"
                for record in self.records
            ),
        )
        self.assertEqual(
            387,
            sum(
                self.regions[record["region_id"]]["type"] == "metro"
                for record in self.records
            ),
        )
        for record in self.records:
            with self.subTest(region_id=record["region_id"]):
                self.assertIn(record["region_id"], self.regions)
                self.assertIn(
                    self.regions[record["region_id"]]["type"], {"state", "metro"}
                )
                self.assertEqual(2024, record["year"])
                self.assertEqual(SOURCE, record["source"])
                for field in COMPONENTS.values():
                    self.assertIsNotNone(record[field])
                    self.assertGreater(float(record[field]), 0)

    def test_unavailable_bea_values_remain_missing(self) -> None:
        self.assertIsNone(_decimal_value("(NA)"))
        self.assertIsNone(_decimal_value("(D)"))
        self.assertIsNone(_decimal_value("--"))

    def test_values_match_bea_published_state_table(self) -> None:
        # BEA table SARPP, 2024 columns, lines 1-5. These exact API values also
        # reconcile to the official SARPP_STATE_2008_2024.csv download.
        expected = {
            "US-STATE-06": {
                "rpp_all_items": "110.720",
                "rpp_goods": "106.098",
                "rpp_housing": "154.346",
                "rpp_utilities": "158.899",
                "rpp_other_services": "102.591",
            },
            "US-STATE-28": {
                "rpp_all_items": "86.953",
                "rpp_goods": "96.219",
                "rpp_housing": "56.456",
                "rpp_utilities": "78.415",
                "rpp_other_services": "96.090",
            },
            "US-STATE-48": {
                "rpp_all_items": "97.057",
                "rpp_goods": "98.083",
                "rpp_housing": "96.503",
                "rpp_utilities": "87.512",
                "rpp_other_services": "97.081",
            },
        }
        for region_id, values in expected.items():
            with self.subTest(region_id=region_id):
                for field, value in values.items():
                    self.assertEqual(value, self.by_region[region_id][field])

    def test_source_manifest_preserves_all_five_bea_series(self) -> None:
        manifest = json.loads(
            (DATA_DIR / "rpp.sources.json").read_text(encoding="utf-8")
        )
        self.assertEqual("U.S. Bureau of Economic Analysis", manifest["publisher"])
        self.assertEqual({"state": "SARPP", "metro": "MARPP"}, manifest["tables"])
        self.assertEqual(SOURCE, manifest["source_tag"])
        self.assertEqual(
            list(COMPONENTS.values()),
            [manifest["components"][str(code)]["field"] for code in COMPONENTS],
        )
        self.assertTrue(manifest["api_url"].startswith("https://apps.bea.gov/api/"))


class RPPMigrationTest(unittest.TestCase):
    def test_migration_is_public_read_only_and_preserves_components(self) -> None:
        migration = next(
            (ROOT / "supabase" / "migrations").glob("*_create_rpp_records.sql")
        )
        sql = migration.read_text(encoding="utf-8").lower()
        self.assertIn("create table public.rpp_records", sql)
        self.assertIn("rpp_utilities numeric", sql)
        self.assertIn("rpp_other_services numeric", sql)
        self.assertIn("source = 'official_bea'", sql)
        self.assertIn("enable row level security", sql)
        self.assertIn(
            "grant select on table public.rpp_records to anon, authenticated", sql
        )
        self.assertNotIn("grant insert on table public.rpp_records to anon", sql)
        self.assertNotIn("grant update on table public.rpp_records to anon", sql)
        self.assertNotIn("grant delete on table public.rpp_records to anon", sql)

    def test_generated_seed_keeps_official_source_tag(self) -> None:
        seed = (ROOT / "supabase" / "seeds" / "rpp.sql").read_text(encoding="utf-8")
        self.assertIn("'official_bea'", seed)
        self.assertNotIn("'modeled'", seed)


if __name__ == "__main__":
    unittest.main()
