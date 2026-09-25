import json
import unittest
from pathlib import Path

from colculator.wages.build import OCCUPATIONS, SOURCE, _annual_wage


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "frontend" / "public" / "data"


class OfficialBLSWageAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads((DATA_DIR / "wages.json").read_text(encoding="utf-8"))
        cls.records = cls.catalog["records"]
        cls.by_key = {
            (record["region_id"], record["soc_code"]): record
            for record in cls.records
        }
        region_catalog = json.loads((DATA_DIR / "regions.json").read_text(encoding="utf-8"))
        cls.regions = {region["id"]: region for region in region_catalog["regions"]}

    def test_all_five_software_occupations_are_ingested_for_states_and_metros(self) -> None:
        self.assertEqual(2025, self.catalog["year"])
        self.assertEqual(SOURCE, self.catalog["source"])
        self.assertEqual(OCCUPATIONS, self.catalog["occupations"])
        self.assertEqual(1416, len(self.records))
        self.assertEqual(len(self.records), len(self.by_key))
        self.assertEqual(
            247,
            sum(self.regions[record["region_id"]]["type"] == "state" for record in self.records),
        )
        self.assertEqual(
            1169,
            sum(self.regions[record["region_id"]]["type"] == "metro" for record in self.records),
        )
        self.assertEqual(set(OCCUPATIONS), {record["soc_code"] for record in self.records})
        for record in self.records:
            with self.subTest(region_id=record["region_id"], soc_code=record["soc_code"]):
                self.assertIn(record["region_id"], self.regions)
                self.assertIn(self.regions[record["region_id"]]["type"], {"state", "metro"})
                self.assertEqual(2025, record["year"])
                self.assertEqual(SOURCE, record["source"])
                for field in ("median_wage", "mean_wage"):
                    if record[field] is not None:
                        self.assertIsInstance(record[field], int)
                        self.assertGreater(record[field], 0)

    def test_values_match_bls_published_state_table(self) -> None:
        # May 2025 OEWS state downloadable table, annual mean and median columns.
        expected = {
            ("US-STATE-06", "15-1252"): (174410, 186770),
            ("US-STATE-28", "15-1252"): (95330, 99840),
            ("US-STATE-48", "15-1252"): (132150, 136450),
        }
        for key, (median, mean) in expected.items():
            with self.subTest(key=key):
                self.assertEqual(median, self.by_key[key]["median_wage"])
                self.assertEqual(mean, self.by_key[key]["mean_wage"])

    def test_bls_suppression_is_explicit_and_never_invented(self) -> None:
        self.assertEqual((None, "not_available"), _annual_wage("*"))
        self.assertEqual((None, "top_coded"), _annual_wage("#"))
        self.assertEqual((None, "not_reported"), _annual_wage(""))
        suppressed = self.by_key[("US-STATE-28", "15-1254")]
        self.assertIsNone(suppressed["median_wage"])
        self.assertIsNone(suppressed["mean_wage"])
        self.assertEqual("not_available", suppressed["median_wage_status"])
        self.assertEqual("not_available", suppressed["mean_wage_status"])

    def test_source_manifest_records_provenance_and_complete_soc_scope(self) -> None:
        manifest = json.loads((DATA_DIR / "wages.sources.json").read_text(encoding="utf-8"))
        self.assertEqual("U.S. Bureau of Labor Statistics", manifest["publisher"])
        self.assertEqual("May 2025", manifest["release"])
        self.assertEqual(SOURCE, manifest["source_tag"])
        self.assertEqual(OCCUPATIONS, manifest["occupations"])
        self.assertEqual({"state": 247, "metro": 1169}, manifest["record_counts"])
        for archive in manifest["archives"].values():
            self.assertTrue(archive["url"].startswith("https://www.bls.gov/oes/"))
            self.assertRegex(archive["sha256"], r"^[0-9a-f]{64}$")


class WageMigrationTest(unittest.TestCase):
    def test_migration_is_public_read_only_and_source_constrained(self) -> None:
        migration = next((ROOT / "supabase" / "migrations").glob("*_create_wage_benchmarks.sql"))
        sql = migration.read_text(encoding="utf-8").lower()
        self.assertIn("create table public.wage_benchmarks", sql)
        self.assertIn("source = 'bls_oews'", sql)
        self.assertIn("enable row level security", sql)
        self.assertIn("grant select on table public.wage_benchmarks to anon, authenticated", sql)
        self.assertNotIn("grant insert on table public.wage_benchmarks to anon", sql)
        self.assertNotIn("grant update on table public.wage_benchmarks to anon", sql)
        self.assertNotIn("grant delete on table public.wage_benchmarks to anon", sql)

    def test_generated_seed_keeps_bls_source_tag(self) -> None:
        seed = (ROOT / "supabase" / "seeds" / "wages.sql").read_text(encoding="utf-8")
        self.assertIn("'bls_oews'", seed)
        self.assertNotIn("'modeled'", seed)


if __name__ == "__main__":
    unittest.main()
