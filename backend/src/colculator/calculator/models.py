"""Typed request and response models for the FR5 calculator."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RPPSource = Literal["official_bea", "modeled"]
HousingProfile = Literal[
    "zillow_typical", "hud_studio", "hud_1br", "hud_2br", "hud_3br"
]
PublicationStatus = Literal[
    "published", "not_available", "top_coded", "not_reported", "unavailable"
]


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nominal_salary: Decimal = Field(gt=0, decimal_places=2)
    destination_region_id: str = Field(min_length=1)
    origin_region_id: str | None = None
    soc_code: str = Field(default="15-1252", pattern=r"^[0-9]{2}-[0-9]{4}$")
    include_state_income_tax: bool = False
    destination_salary: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    housing_profile: HousingProfile = "zillow_typical"
    origin_monthly_housing: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    destination_monthly_housing: Decimal | None = Field(
        default=None, ge=0, decimal_places=2
    )


class RPPResolution(BaseModel):
    requested_region_id: str
    requested_region_name: str
    effective_region_id: str
    effective_region_name: str
    year: int
    source: RPPSource
    rpp_all_items: Decimal = Field(gt=0)
    rpp_housing: Decimal | None = Field(default=None, gt=0)
    rpp_goods: Decimal | None = Field(default=None, gt=0)
    rpp_utilities: Decimal | None = Field(default=None, gt=0)
    rpp_other_services: Decimal | None = Field(default=None, gt=0)
    confidence_interval: tuple[Decimal, Decimal] | None = None
    model_version: str | None = None

    @model_validator(mode="after")
    def modeled_values_require_uncertainty_metadata(self) -> "RPPResolution":
        if self.source != "modeled":
            return self
        if self.confidence_interval is None or not self.model_version:
            raise ValueError(
                "modeled RPP values require a confidence interval and model version"
            )
        lower, upper = self.confidence_interval
        if lower <= 0 or lower > self.rpp_all_items or self.rpp_all_items > upper:
            raise ValueError(
                "modeled RPP confidence interval must contain the positive estimate"
            )
        return self


class RegionResult(BaseModel):
    requested_region_id: str
    requested_region_name: str
    effective_rpp_region_id: str
    effective_rpp_region_name: str
    rpp_year: int
    rpp_all_items: Decimal
    rpp_source: RPPSource
    confidence_interval: tuple[Decimal, Decimal] | None
    model_version: str | None


class CategoryResult(BaseModel):
    category: Literal["housing", "goods", "utilities", "other_services"]
    category_group: Literal["housing", "goods", "services"]
    status: Literal["available", "unavailable"]
    origin_rpp: Decimal | None
    destination_rpp: Decimal | None
    equivalent_salary: Decimal | None
    origin_source: RPPSource
    destination_source: RPPSource
    unavailable_reason: str | None = None


class DestinationWageResult(BaseModel):
    requested_region_id: str
    benchmark_region_id: str | None
    soc_code: str
    year: int | None
    median_wage: Decimal | None
    publication_status: PublicationStatus
    source: Literal["bls_oews"] | None
    unavailable_reason: str | None = None


class TaxAdjustmentResult(BaseModel):
    requested: bool
    status: Literal["not_requested", "available", "unavailable"]
    adjusted_salary: None = None
    unavailable_reason: str | None = None


class TaxEstimateResult(BaseModel):
    tax_year: int
    filing_status: Literal["single"]
    federal_income_tax: Decimal
    payroll_tax: Decimal
    state_income_tax: Decimal
    local_income_tax: Decimal
    local_income_tax_status: Literal["included_nyc", "not_modeled"]
    total_estimated_tax: Decimal
    take_home_pay: Decimal
    federal_source: Literal["irs_2026"]
    federal_source_url: str
    payroll_source_url: str
    state_source: Literal["tax_foundation_2026"]
    state_source_url: str
    local_source: Literal["nyc_tax_2026"] | None = None
    local_source_url: str | None = None


class HousingEstimateResult(BaseModel):
    monthly_cost: Decimal
    annual_cost: Decimal
    profile: HousingProfile | Literal["user_provided"]
    source: Literal["zillow_research", "hud_fmr", "user_provided"]
    source_year: int | None
    source_url: str | None


class OfferValueResult(BaseModel):
    region_id: str
    region_name: str
    gross_salary: Decimal
    taxes: TaxEstimateResult
    housing: HousingEstimateResult
    spendable_after_housing: Decimal
    comparable_disposable_income: Decimal


class OfferComparisonResult(BaseModel):
    status: Literal["available", "unavailable"]
    origin_offer: OfferValueResult | None = None
    destination_offer: OfferValueResult | None = None
    destination_break_even_offer: OfferValueResult | None = None
    destination_break_even_salary: Decimal | None = None
    better_offer: Literal["origin", "destination", "equivalent", "not_compared"] | None = None
    annual_advantage: Decimal | None = None
    nonhousing_cost_ratio: Decimal | None = None
    housing_expenditure_weight: Decimal = Decimal("0.226")
    methodology: str
    unavailable_reason: str | None = None
    limitations: list[str] = Field(default_factory=list)


class CalculationResponse(BaseModel):
    nominal_salary: Decimal
    adjusted_salary: Decimal
    calculation: Literal[
        "nominal_salary * (destination_rpp_all_items / origin_rpp_all_items)"
    ]
    origin: RegionResult
    destination: RegionResult
    category_breakdown: list[CategoryResult]
    category_breakdown_note: str
    destination_wage_benchmark: DestinationWageResult
    state_income_tax_adjustment: TaxAdjustmentResult
    offer_comparison: OfferComparisonResult


class WageRecord(BaseModel):
    region_id: str
    soc_code: str
    median_wage: Decimal | None
    median_wage_status: PublicationStatus
    year: int
    source: Literal["bls_oews"]


class CountyCostProfile(BaseModel):
    county_fips: str
    year: int
    zori: Decimal | None
    hud_fmr_studio: Decimal
    hud_fmr_1br: Decimal
    hud_fmr_2br: Decimal
    hud_fmr_3br: Decimal
    zillow_observation: str | None
    hud_fiscal_year: int


class StateIncomeTaxRule(BaseModel):
    state_region_id: str
    state_name: str
    tax_year: int
    brackets: list[tuple[Decimal, Decimal]]
    standard_deduction: Decimal
    personal_exemption: Decimal
    standard_credit: Decimal
    exemption_credit: Decimal
    no_wage_income_tax: bool
    source_url: str
