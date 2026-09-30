"""FR5 calculation service with source and availability propagation."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from math import exp, log
from typing import Protocol

from .models import (
    CalculationRequest,
    CalculationResponse,
    CategoryResult,
    CountyCostProfile,
    DestinationWageResult,
    HousingEstimateResult,
    OfferComparisonResult,
    OfferValueResult,
    RPPResolution,
    RegionResult,
    StateIncomeTaxRule,
    TaxAdjustmentResult,
    TaxEstimateResult,
    WageRecord,
)


MONEY = Decimal("0.01")
CATEGORY_FIELDS = (
    ("housing", "housing", "rpp_housing"),
    ("goods", "goods", "rpp_goods"),
    ("utilities", "services", "rpp_utilities"),
    ("other_services", "services", "rpp_other_services"),
)
CATEGORY_NOTE = (
    "Each category is an independent equivalent-salary comparison using its "
    "published RPP. Values are not combined into a weighted contribution because "
    "the source data does not provide household-specific spending weights."
)
FEDERAL_TAX_SOURCE_URL = (
    "https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-"
    "tax-year-2026-including-amendments-from-the-one-big-beautiful-bill"
)
PAYROLL_TAX_SOURCE_URL = "https://www.irs.gov/publications/p15"
ZILLOW_SOURCE_URL = "https://www.zillow.com/research/data/"
HUD_SOURCE_URL = "https://www.huduser.gov/portal/datasets/fmr.html"
NYC_TAX_SOURCE_URL = "https://www.tax.ny.gov/pdf/publications/withholding/nys50_t_nyc.pdf"
HOUSING_EXPENDITURE_WEIGHT = Decimal("0.226")
FEDERAL_STANDARD_DEDUCTION = Decimal("16100")
SOCIAL_SECURITY_WAGE_BASE = Decimal("184500")
FEDERAL_BRACKETS = (
    (Decimal("0"), Decimal("0.10")),
    (Decimal("12400"), Decimal("0.12")),
    (Decimal("50400"), Decimal("0.22")),
    (Decimal("105700"), Decimal("0.24")),
    (Decimal("201775"), Decimal("0.32")),
    (Decimal("256225"), Decimal("0.35")),
    (Decimal("640600"), Decimal("0.37")),
)
NYC_COUNTY_FIPS = {"36005", "36047", "36061", "36081", "36085"}
NYC_BRACKETS = (
    (Decimal("0"), Decimal("0.03078")),
    (Decimal("12000"), Decimal("0.03762")),
    (Decimal("25000"), Decimal("0.03819")),
    (Decimal("50000"), Decimal("0.03876")),
)
OFFER_METHODOLOGY = (
    "2026 single-filer take-home pay minus a sourced annual housing estimate; "
    "the remaining amount is converted to origin-location purchasing power using "
    "a nonhousing ratio derived from BEA all-items and housing RPPs."
)


class CalculatorRepository(Protocol):
    def resolve_rpp(self, region_id: str | None) -> RPPResolution: ...

    def find_wage(self, region_id: str, soc_code: str) -> WageRecord | None: ...

    def resolve_county_cost_profile(
        self, region_id: str | None
    ) -> CountyCostProfile | None: ...

    def resolve_state_tax_rule(
        self, region_id: str | None
    ) -> StateIncomeTaxRule | None: ...


class SalaryCalculator:
    def __init__(self, repository: CalculatorRepository) -> None:
        self._repository = repository

    def calculate(self, request: CalculationRequest) -> CalculationResponse:
        origin = self._repository.resolve_rpp(request.origin_region_id)
        destination = self._repository.resolve_rpp(request.destination_region_id)
        adjusted_salary = self._money(
            request.nominal_salary
            * destination.rpp_all_items
            / origin.rpp_all_items
        )
        offer_comparison = self._offer_comparison(request, origin, destination)
        return CalculationResponse(
            nominal_salary=self._money(request.nominal_salary),
            adjusted_salary=adjusted_salary,
            calculation=(
                "nominal_salary * (destination_rpp_all_items / origin_rpp_all_items)"
            ),
            origin=self._region_result(origin),
            destination=self._region_result(destination),
            category_breakdown=self._category_breakdown(
                request.nominal_salary, origin, destination
            ),
            category_breakdown_note=CATEGORY_NOTE,
            destination_wage_benchmark=self._wage_result(
                destination, request.soc_code
            ),
            state_income_tax_adjustment=self._tax_result(request, offer_comparison),
            offer_comparison=offer_comparison,
        )

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(MONEY, rounding=ROUND_HALF_UP)

    @staticmethod
    def _region_result(resolution: RPPResolution) -> RegionResult:
        return RegionResult(
            requested_region_id=resolution.requested_region_id,
            requested_region_name=resolution.requested_region_name,
            effective_rpp_region_id=resolution.effective_region_id,
            effective_rpp_region_name=resolution.effective_region_name,
            rpp_year=resolution.year,
            rpp_all_items=resolution.rpp_all_items,
            rpp_source=resolution.source,
            confidence_interval=resolution.confidence_interval,
            model_version=resolution.model_version,
        )

    def _category_breakdown(
        self,
        salary: Decimal,
        origin: RPPResolution,
        destination: RPPResolution,
    ) -> list[CategoryResult]:
        results: list[CategoryResult] = []
        for category, group, field in CATEGORY_FIELDS:
            origin_rpp = getattr(origin, field)
            destination_rpp = getattr(destination, field)
            if origin_rpp is None or destination_rpp is None:
                results.append(
                    CategoryResult(
                        category=category,
                        category_group=group,
                        status="unavailable",
                        origin_rpp=origin_rpp,
                        destination_rpp=destination_rpp,
                        equivalent_salary=None,
                        origin_source=origin.source,
                        destination_source=destination.source,
                        unavailable_reason=(
                            "The source record does not publish this category; no value "
                            "was inferred."
                        ),
                    )
                )
                continue
            results.append(
                CategoryResult(
                    category=category,
                    category_group=group,
                    status="available",
                    origin_rpp=origin_rpp,
                    destination_rpp=destination_rpp,
                    equivalent_salary=self._money(
                        salary * destination_rpp / origin_rpp
                    ),
                    origin_source=origin.source,
                    destination_source=destination.source,
                )
            )
        return results

    def _wage_result(
        self, destination: RPPResolution, soc_code: str
    ) -> DestinationWageResult:
        wage = self._repository.find_wage(destination.effective_region_id, soc_code)
        if wage is None:
            return DestinationWageResult(
                requested_region_id=destination.requested_region_id,
                benchmark_region_id=None,
                soc_code=soc_code,
                year=None,
                median_wage=None,
                publication_status="unavailable",
                source=None,
                unavailable_reason=(
                    "No BLS OEWS median wage is published for this occupation and "
                    "effective destination region."
                ),
            )
        return DestinationWageResult(
            requested_region_id=destination.requested_region_id,
            benchmark_region_id=wage.region_id,
            soc_code=soc_code,
            year=wage.year,
            median_wage=wage.median_wage,
            publication_status=wage.median_wage_status,
            source=wage.source,
            unavailable_reason=(
                None
                if wage.median_wage is not None
                else "BLS did not publish an exact median wage for this record."
            ),
        )

    def _offer_comparison(
        self,
        request: CalculationRequest,
        origin: RPPResolution,
        destination: RPPResolution,
    ) -> OfferComparisonResult:
        origin_cost = self._repository.resolve_county_cost_profile(
            request.origin_region_id
        )
        destination_cost = self._repository.resolve_county_cost_profile(
            request.destination_region_id
        )
        if origin_cost is None or destination_cost is None:
            return OfferComparisonResult(
                status="unavailable",
                methodology=OFFER_METHODOLOGY,
                unavailable_reason=(
                    "Choose an origin county and a destination county. State and "
                    "national selections do not have a single defensible housing cost."
                ),
                limitations=self._offer_limitations(),
            )
        if origin.rpp_housing is None or destination.rpp_housing is None:
            return OfferComparisonResult(
                status="unavailable",
                methodology=OFFER_METHODOLOGY,
                unavailable_reason=(
                    "A housing RPP is unavailable for one of these counties, so the "
                    "nonhousing price ratio cannot be estimated without inventing data."
                ),
                limitations=self._offer_limitations(),
            )
        origin_tax_rule = self._repository.resolve_state_tax_rule(
            request.origin_region_id
        )
        destination_tax_rule = self._repository.resolve_state_tax_rule(
            request.destination_region_id
        )
        if origin_tax_rule is None or destination_tax_rule is None:
            return OfferComparisonResult(
                status="unavailable",
                methodology=OFFER_METHODOLOGY,
                unavailable_reason="A sourced state income-tax rule is unavailable.",
                limitations=self._offer_limitations(),
            )

        origin_housing, destination_housing = self._housing_pair(
            request, origin_cost, destination_cost
        )
        nonhousing_ratio = self._nonhousing_ratio(origin, destination)
        origin_offer = self._offer_value(
            region_id=origin.requested_region_id,
            region_name=origin.requested_region_name,
            county_fips=origin_cost.county_fips,
            salary=request.nominal_salary,
            tax_rule=origin_tax_rule,
            housing=origin_housing,
            purchasing_power_ratio=Decimal(1),
        )
        break_even = self._break_even_salary(
            target=origin_offer.comparable_disposable_income,
            region_id=destination.requested_region_id,
            region_name=destination.requested_region_name,
            county_fips=destination_cost.county_fips,
            tax_rule=destination_tax_rule,
            housing=destination_housing,
            purchasing_power_ratio=nonhousing_ratio,
            starting_salary=request.nominal_salary,
        )
        break_even_offer = self._offer_value(
            region_id=destination.requested_region_id,
            region_name=destination.requested_region_name,
            county_fips=destination_cost.county_fips,
            salary=break_even,
            tax_rule=destination_tax_rule,
            housing=destination_housing,
            purchasing_power_ratio=nonhousing_ratio,
        )
        destination_offer = None
        better_offer = "not_compared"
        advantage = None
        if request.destination_salary is not None:
            destination_offer = self._offer_value(
                region_id=destination.requested_region_id,
                region_name=destination.requested_region_name,
                county_fips=destination_cost.county_fips,
                salary=request.destination_salary,
                tax_rule=destination_tax_rule,
                housing=destination_housing,
                purchasing_power_ratio=nonhousing_ratio,
            )
            advantage = self._money(
                destination_offer.comparable_disposable_income
                - origin_offer.comparable_disposable_income
            )
            if abs(advantage) < Decimal("1.00"):
                better_offer = "equivalent"
            elif advantage > 0:
                better_offer = "destination"
            else:
                better_offer = "origin"

        return OfferComparisonResult(
            status="available",
            origin_offer=origin_offer,
            destination_offer=destination_offer,
            destination_break_even_offer=break_even_offer,
            destination_break_even_salary=break_even,
            better_offer=better_offer,
            annual_advantage=advantage,
            nonhousing_cost_ratio=nonhousing_ratio.quantize(Decimal("0.0001")),
            methodology=OFFER_METHODOLOGY,
            limitations=self._offer_limitations(),
        )

    def _housing_pair(
        self,
        request: CalculationRequest,
        origin: CountyCostProfile,
        destination: CountyCostProfile,
    ) -> tuple[HousingEstimateResult, HousingEstimateResult]:
        profile = request.housing_profile
        if (
            profile == "zillow_typical"
            and request.origin_monthly_housing is None
            and request.destination_monthly_housing is None
            and (origin.zori is None or destination.zori is None)
        ):
            profile = "hud_1br"
        return (
            self._housing_estimate(origin, profile, request.origin_monthly_housing),
            self._housing_estimate(
                destination, profile, request.destination_monthly_housing
            ),
        )

    def _housing_estimate(
        self,
        cost: CountyCostProfile,
        profile: str,
        override: Decimal | None,
    ) -> HousingEstimateResult:
        if override is not None:
            monthly = override
            return HousingEstimateResult(
                monthly_cost=self._money(monthly),
                annual_cost=self._money(monthly * 12),
                profile="user_provided",
                source="user_provided",
                source_year=None,
                source_url=None,
            )
        if profile == "zillow_typical" and cost.zori is not None:
            source_year = (
                int(cost.zillow_observation[:4])
                if cost.zillow_observation
                else cost.year
            )
            return HousingEstimateResult(
                monthly_cost=self._money(cost.zori),
                annual_cost=self._money(cost.zori * 12),
                profile="zillow_typical",
                source="zillow_research",
                source_year=source_year,
                source_url=ZILLOW_SOURCE_URL,
            )
        hud_field = {
            "hud_studio": "hud_fmr_studio",
            "hud_1br": "hud_fmr_1br",
            "hud_2br": "hud_fmr_2br",
            "hud_3br": "hud_fmr_3br",
        }.get(profile, "hud_fmr_1br")
        monthly = getattr(cost, hud_field)
        resolved_profile = profile if profile.startswith("hud_") else "hud_1br"
        return HousingEstimateResult(
            monthly_cost=self._money(monthly),
            annual_cost=self._money(monthly * 12),
            profile=resolved_profile,
            source="hud_fmr",
            source_year=cost.hud_fiscal_year,
            source_url=HUD_SOURCE_URL,
        )

    @staticmethod
    def _nonhousing_ratio(
        origin: RPPResolution, destination: RPPResolution
    ) -> Decimal:
        assert origin.rpp_housing is not None
        assert destination.rpp_housing is not None
        all_ratio = float(destination.rpp_all_items / origin.rpp_all_items)
        housing_ratio = float(destination.rpp_housing / origin.rpp_housing)
        weight = float(HOUSING_EXPENDITURE_WEIGHT)
        ratio = exp((log(all_ratio) - weight * log(housing_ratio)) / (1 - weight))
        return Decimal(str(ratio))

    def _offer_value(
        self,
        *,
        region_id: str,
        region_name: str,
        county_fips: str,
        salary: Decimal,
        tax_rule: StateIncomeTaxRule,
        housing: HousingEstimateResult,
        purchasing_power_ratio: Decimal,
    ) -> OfferValueResult:
        taxes = self._tax_estimate(salary, tax_rule, county_fips)
        spendable = self._money(taxes.take_home_pay - housing.annual_cost)
        return OfferValueResult(
            region_id=region_id,
            region_name=region_name,
            gross_salary=self._money(salary),
            taxes=taxes,
            housing=housing,
            spendable_after_housing=spendable,
            comparable_disposable_income=self._money(
                spendable / purchasing_power_ratio
            ),
        )

    def _tax_estimate(
        self,
        salary: Decimal,
        state_rule: StateIncomeTaxRule,
        county_fips: str,
    ) -> TaxEstimateResult:
        federal_taxable = max(Decimal(0), salary - FEDERAL_STANDARD_DEDUCTION)
        federal = self._progressive_tax(federal_taxable, FEDERAL_BRACKETS)
        payroll = (
            min(salary, SOCIAL_SECURITY_WAGE_BASE) * Decimal("0.062")
            + salary * Decimal("0.0145")
            + max(Decimal(0), salary - Decimal("200000")) * Decimal("0.009")
        )
        if state_rule.no_wage_income_tax:
            state = Decimal(0)
        else:
            state_taxable = max(
                Decimal(0),
                salary
                - state_rule.standard_deduction
                - state_rule.personal_exemption,
            )
            state = self._progressive_tax(state_taxable, state_rule.brackets)
            state = max(
                Decimal(0),
                state - state_rule.standard_credit - state_rule.exemption_credit,
            )
        local = Decimal(0)
        local_source = None
        local_status = "not_modeled"
        if county_fips in NYC_COUNTY_FIPS:
            local_taxable = max(Decimal(0), salary - Decimal("8000"))
            local = self._progressive_tax(local_taxable, NYC_BRACKETS)
            local_source = "nyc_tax_2026"
            local_status = "included_nyc"
        federal = self._money(federal)
        payroll = self._money(payroll)
        state = self._money(state)
        local = self._money(local)
        total = self._money(federal + payroll + state + local)
        return TaxEstimateResult(
            tax_year=2026,
            filing_status="single",
            federal_income_tax=federal,
            payroll_tax=payroll,
            state_income_tax=state,
            local_income_tax=local,
            local_income_tax_status=local_status,
            total_estimated_tax=total,
            take_home_pay=self._money(salary - total),
            federal_source="irs_2026",
            federal_source_url=FEDERAL_TAX_SOURCE_URL,
            payroll_source_url=PAYROLL_TAX_SOURCE_URL,
            state_source="tax_foundation_2026",
            state_source_url=state_rule.source_url,
            local_source=local_source,
            local_source_url=NYC_TAX_SOURCE_URL if local_source else None,
        )

    @staticmethod
    def _progressive_tax(
        taxable_income: Decimal,
        brackets: tuple[tuple[Decimal, Decimal], ...]
        | list[tuple[Decimal, Decimal]],
    ) -> Decimal:
        tax = Decimal(0)
        ordered = sorted(brackets)
        for index, (threshold, rate) in enumerate(ordered):
            if taxable_income <= threshold:
                continue
            upper = (
                ordered[index + 1][0]
                if index + 1 < len(ordered)
                else taxable_income
            )
            tax += (min(taxable_income, upper) - threshold) * rate
        return tax

    def _break_even_salary(
        self,
        *,
        target: Decimal,
        region_id: str,
        region_name: str,
        county_fips: str,
        tax_rule: StateIncomeTaxRule,
        housing: HousingEstimateResult,
        purchasing_power_ratio: Decimal,
        starting_salary: Decimal,
    ) -> Decimal:
        lower = Decimal(0)
        upper = max(Decimal("100000"), starting_salary * 2)

        def comparable(salary: Decimal) -> Decimal:
            return self._offer_value(
                region_id=region_id,
                region_name=region_name,
                county_fips=county_fips,
                salary=max(Decimal("0.01"), salary),
                tax_rule=tax_rule,
                housing=housing,
                purchasing_power_ratio=purchasing_power_ratio,
            ).comparable_disposable_income

        while comparable(upper) < target and upper < Decimal("10000000"):
            upper *= 2
        for _ in range(80):
            midpoint = (lower + upper) / 2
            if comparable(midpoint) < target:
                lower = midpoint
            else:
                upper = midpoint
        return self._money(upper)

    @staticmethod
    def _offer_limitations() -> list[str]:
        return [
            "Estimates assume a single filer taking standard deductions, with no "
            "dependents, credits, retirement contributions, bonuses, or benefits.",
            "Local income tax is included for New York City residents only; other "
            "municipal income taxes are marked not modeled rather than assumed zero.",
            "The nonhousing ratio is an approximation calibrated with BEA's "
            "historical 2017 rent weight of 22.6%, not a current expenditure "
            "weight or an exact decomposition of BEA's multilateral index.",
            "Comparable income means money after estimated taxes and housing, "
            "adjusted for nonhousing prices—not savings after all household bills. "
            "No confidence interval for the overall offer comparison is available.",
            "State tax estimates omit income-dependent deduction phaseouts, "
            "recapture provisions, and household-specific adjustments.",
        ]

    @staticmethod
    def _tax_result(
        request: CalculationRequest,
        comparison: OfferComparisonResult,
    ) -> TaxAdjustmentResult:
        if comparison.status == "available":
            return TaxAdjustmentResult(requested=True, status="available")
        if request.include_state_income_tax:
            return TaxAdjustmentResult(
                requested=True,
                status="unavailable",
                unavailable_reason=comparison.unavailable_reason,
            )
        return TaxAdjustmentResult(requested=False, status="not_requested")
