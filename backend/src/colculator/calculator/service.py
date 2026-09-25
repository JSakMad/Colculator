"""FR5 calculation service with source and availability propagation."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

from .models import (
    CalculationRequest,
    CalculationResponse,
    CategoryResult,
    DestinationWageResult,
    RPPResolution,
    RegionResult,
    TaxAdjustmentResult,
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
TAX_UNAVAILABLE_REASON = (
    "State income tax adjustment is unavailable until a tax dataset and calculation "
    "assumptions are sourced; the RPP-adjusted salary is unchanged."
)


class CalculatorRepository(Protocol):
    def resolve_rpp(self, region_id: str | None) -> RPPResolution: ...

    def find_wage(self, region_id: str, soc_code: str) -> WageRecord | None: ...


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
            state_income_tax_adjustment=self._tax_result(
                request.include_state_income_tax
            ),
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

    @staticmethod
    def _tax_result(requested: bool) -> TaxAdjustmentResult:
        if requested:
            return TaxAdjustmentResult(
                requested=True,
                status="unavailable",
                unavailable_reason=TAX_UNAVAILABLE_REASON,
            )
        return TaxAdjustmentResult(requested=False, status="not_requested")
