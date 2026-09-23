import gzip
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "frontend" / "public" / "data"


class RegionHierarchyAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads((DATA_DIR / "regions.json").read_text(encoding="utf-8"))
        cls.regions = cls.catalog["regions"]
        cls.by_id = {region["id"]: region for region in cls.regions}
        cls.counties = [region for region in cls.regions if region["type"] == "county"]
        cls.states = [region for region in cls.regions if region["type"] == "state"]
        cls.metros = [region for region in cls.regions if region["type"] == "metro"]

    def test_every_county_resolves_to_exactly_one_parent_state(self) -> None:
        state_ids = {region["id"] for region in self.states}
        self.assertEqual(51, len(state_ids))
        self.assertEqual(3_144, len(self.counties))
        for county in self.counties:
            with self.subTest(county_fips=county["fips"]):
                self.assertIn(county["parent_region_id"], state_ids)
                self.assertEqual(
                    county["fips"][:2],
                    self.by_id[county["parent_region_id"]]["fips"],
                )

    def test_msa_membership_matches_official_omb_spot_checks(self) -> None:
        # July 2023 OMB delineation list, Metropolitan Statistical Area rows.
        expected = {
            "06001": "US-METRO-41860",  # Alameda County, CA
            "17031": "US-METRO-16980",  # Cook County, IL
            "36061": "US-METRO-35620",  # New York County, NY
            "48453": "US-METRO-12420",  # Travis County, TX
        }
        counties_by_fips = {county["fips"]: county for county in self.counties}
        for fips, msa_id in expected.items():
            with self.subTest(county_fips=fips):
                self.assertEqual(msa_id, counties_by_fips[fips]["msa_id"])
                self.assertIn(msa_id, self.by_id)
                self.assertEqual("metro", self.by_id[msa_id]["type"])

        # Alpine County belongs to a micropolitan area, not an MSA; FR1's msa_id
        # therefore remains null rather than silently widening the definition.
        self.assertIsNone(counties_by_fips["06003"]["msa_id"])

    def test_region_ids_and_source_references_are_complete(self) -> None:
        self.assertEqual(len(self.regions), len(self.by_id))
        for region in self.regions:
            with self.subTest(region_id=region["id"]):
                self.assertEqual("US", region["country_code"])
                self.assertTrue(region["is_interactive"])
                if region["type"] in {"state", "county"}:
                    self.assertIsNotNone(region["geometry_ref"])
                else:
                    self.assertIsNone(region["geometry_ref"])
                if region["msa_id"] is not None:
                    self.assertIn(region["msa_id"], self.by_id)
                    self.assertEqual("metro", self.by_id[region["msa_id"]]["type"])

        sources = json.loads(
            (DATA_DIR / "regions.sources.json").read_text(encoding="utf-8")
        )
        generated = sources["generated_from"]
        self.assertEqual(3, len(generated))
        for source in generated:
            self.assertTrue(source["url"].startswith("https://www2.census.gov/"))
            self.assertEqual(64, len(source["sha256"]))


class RegionGeometryAcceptanceTest(unittest.TestCase):
    def _topology(self, filename: str) -> tuple[dict, bytes]:
        payload = (DATA_DIR / "geometry" / filename).read_bytes()
        return json.loads(payload), payload

    def test_topojson_has_one_geometry_per_state_and_county(self) -> None:
        states, _ = self._topology("us-states.topo.json")
        counties, _ = self._topology("us-counties.topo.json")
        state_geometries = states["objects"]["states"]["geometries"]
        county_geometries = counties["objects"]["counties"]["geometries"]

        self.assertEqual("Topology", states["type"])
        self.assertEqual("Topology", counties["type"])
        self.assertEqual(51, len(state_geometries))
        self.assertEqual(3_144, len(county_geometries))
        self.assertEqual(51, len({geometry["id"] for geometry in state_geometries}))
        self.assertEqual(3_144, len({geometry["id"] for geometry in county_geometries}))
        self.assertIn("transform", states)
        self.assertIn("transform", counties)

    def test_geometry_payload_is_web_performant(self) -> None:
        _, states = self._topology("us-states.topo.json")
        _, counties = self._topology("us-counties.topo.json")

        self.assertLess(len(states), 3_000_000)
        self.assertLess(len(counties), 3_000_000)
        self.assertLess(len(gzip.compress(states, compresslevel=9)), 100_000)
        self.assertLess(len(gzip.compress(counties, compresslevel=9)), 500_000)


class RegionMigrationTest(unittest.TestCase):
    def test_migration_exposes_regions_read_only_with_rls(self) -> None:
        migration = next((ROOT / "supabase" / "migrations").glob("*_create_regions.sql"))
        sql = migration.read_text(encoding="utf-8").lower()
        self.assertIn("create table public.regions", sql)
        self.assertIn("enable row level security", sql)
        self.assertIn("grant select on table public.regions to anon, authenticated", sql)
        self.assertNotIn("grant insert", sql)
        self.assertNotIn("grant update", sql)
        self.assertNotIn("grant delete", sql)


if __name__ == "__main__":
    unittest.main()
