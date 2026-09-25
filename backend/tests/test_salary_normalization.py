import unittest
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from colculator.api import app, get_calculator
from colculator.calculator.models import (
    CalculationRequest,
    RPPResolution,
    WageRecord,
)
from colculator.calculator.repository import CatalogRepository
from colculator.calculator.service import SalaryCalculator


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "frontend" / "public" / "data"


class SalaryNormalizationAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.calculator = SalaryCalculator(CatalogRepository(DATA_DIR))

    def test_same_region_preserves_nominal_salary_exactly(self) -> None:
        result = self.calculator.calculate(
            CalculationRequest(
                nominal_salary=Decimal("123456.78"),
                origin_region_id="US-STATE-06",
                destination_region_id="US-STATE-06",
            )
        )
        self.assertEqual(Decimal("123456.78"), result.adjusted_salary)
        for category in result.category_breakdown:
            self.assertEqual(Decimal("123456.78"), category.equivalent_salary)

    def test_known_official_rpp_calculation_and_bls_benchmark(self) -> None:
        result = self.calculator.calculate(
            CalculationRequest(
                nominal_salary=Decimal("100000.00"),
                origin_region_id="US-STATE-28",
                destination_region_id="US-STATE-06",
            )
        )
        self.assertEqual(Decimal("127333.16"), result.adjusted_salary)
        self.assertEqual("official_bea", result.origin.rpp_source)
        self.assertEqual("official_bea", result.destination.rpp_source)
        self.assertEqual(Decimal("174410"), result.destination_wage_benchmark.median_wage)
        self.assertEqual("bls_oews", result.destination_wage_benchmark.source)
        self.assertEqual("15-1252", result.destination_wage_benchmark.soc_code)

    def test_unspecified_origin_uses_official_national_average(self) -> None:
        result = self.calculator.calculate(
            CalculationRequest(
                nominal_salary=Decimal("100000.00"),
                destination_region_id="US-STATE-06",
            )
        )
        self.assertEqual("US-NATIONAL", result.origin.requested_region_id)
        self.assertEqual(Decimal("100.000"), result.origin.rpp_all_items)
        self.assertEqual("official_bea", result.origin.rpp_source)
        self.assertEqual(Decimal("110720.00"), result.adjusted_salary)

    def test_county_with_official_metro_uses_metro_rpp_and_wage(self) -> None:
        result = self.calculator.calculate(
            CalculationRequest(
                nominal_salary=Decimal("100000.00"),
                destination_region_id="US-COUNTY-06075",
            )
        )
        self.assertEqual("US-COUNTY-06075", result.destination.requested_region_id)
        self.assertEqual("US-METRO-41860", result.destination.effective_rpp_region_id)
        self.assertEqual("official_bea", result.destination.rpp_source)
        self.assertEqual(
            "US-METRO-41860",
            result.destination_wage_benchmark.benchmark_region_id,
        )

    def test_tax_request_is_explicitly_unavailable_and_never_blended(self) -> None:
        base = self.calculator.calculate(
            CalculationRequest(
                nominal_salary=Decimal("100000.00"),
                destination_region_id="US-STATE-06",
            )
        )
        requested = self.calculator.calculate(
            CalculationRequest(
                nominal_salary=Decimal("100000.00"),
                destination_region_id="US-STATE-06",
                include_state_income_tax=True,
            )
        )
        self.assertEqual(base.adjusted_salary, requested.adjusted_salary)
        self.assertEqual("unavailable", requested.state_income_tax_adjustment.status)
        self.assertIsNone(requested.state_income_tax_adjustment.adjusted_salary)

    def test_modeled_rpp_cannot_omit_confidence_metadata(self) -> None:
        with self.assertRaises(ValidationError):
            RPPResolution(
                requested_region_id="US-COUNTY-99999",
                requested_region_name="Example County",
                effective_region_id="US-COUNTY-99999",
                effective_region_name="Example County",
                year=2024,
                source="modeled",
                rpp_all_items=Decimal("91.25"),
            )


class ModeledRepository:
    def resolve_rpp(self, region_id: str | None) -> RPPResolution:
        if region_id is None:
            return RPPResolution(
                requested_region_id="US-NATIONAL",
                requested_region_name="United States national average",
                effective_region_id="US-NATIONAL",
                effective_region_name="United States national average",
                year=2024,
                source="official_bea",
                rpp_all_items=Decimal("100"),
                rpp_housing=Decimal("100"),
                rpp_goods=Decimal("100"),
                rpp_utilities=Decimal("100"),
                rpp_other_services=Decimal("100"),
            )
        return RPPResolution(
            requested_region_id=region_id,
            requested_region_name="Example County",
            effective_region_id=region_id,
            effective_region_name="Example County",
            year=2024,
            source="modeled",
            rpp_all_items=Decimal("91.25"),
            rpp_housing=Decimal("82.5"),
            confidence_interval=(Decimal("87.10"), Decimal("95.40")),
            model_version="fixture-v1",
        )

    def find_wage(self, region_id: str, soc_code: str) -> WageRecord | None:
        return None


class SalaryNormalizationAPIContractTest(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_ui_facing_response_preserves_modeled_source_and_confidence(self) -> None:
        app.dependency_overrides[get_calculator] = lambda: SalaryCalculator(
            ModeledRepository()
        )
        with TestClient(app) as client:
            response = client.post(
                "/v1/calculate",
                json={
                    "nominal_salary": "100000.00",
                    "destination_region_id": "US-COUNTY-99999",
                },
            )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("modeled", payload["destination"]["rpp_source"])
        self.assertEqual(["87.10", "95.40"], payload["destination"]["confidence_interval"])
        self.assertEqual("fixture-v1", payload["destination"]["model_version"])
        goods = next(
            item for item in payload["category_breakdown"] if item["category"] == "goods"
        )
        self.assertEqual("unavailable", goods["status"])
        self.assertIsNone(goods["equivalent_salary"])

    def test_unknown_region_returns_structured_404(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/v1/calculate",
                json={
                    "nominal_salary": "100000.00",
                    "destination_region_id": "US-STATE-99",
                },
            )
        self.assertEqual(404, response.status_code)
        self.assertEqual("unknown_region", response.json()["detail"]["code"])
        self.assertEqual("US-STATE-99", response.json()["detail"]["region_id"])


if __name__ == "__main__":
    unittest.main()
