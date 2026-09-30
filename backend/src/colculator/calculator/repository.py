"""Read-only repository over the committed official-data artifacts."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from .models import CountyCostProfile, RPPResolution, StateIncomeTaxRule, WageRecord


NATIONAL_REGION_ID = "US-NATIONAL"
NATIONAL_REGION_NAME = "United States national average"
NATIONAL_RPP = Decimal("100.000")


class UnknownRegionError(LookupError):
    """The requested region is not in the FR1 catalog."""


class RPPUnavailableError(LookupError):
    """The region is known, but no official or modeled RPP is available."""


class CatalogRepository:
    """Resolve regions to exact, source-tagged RPP and wage records."""

    def __init__(self, data_dir: Path) -> None:
        regions_payload = json.loads(
            (data_dir / "regions.json").read_text(encoding="utf-8")
        )
        rpp_payload = json.loads((data_dir / "rpp.json").read_text(encoding="utf-8"))
        wages_payload = json.loads((data_dir / "wages.json").read_text(encoding="utf-8"))
        self._regions = {
            str(region["id"]): region
            for region in regions_payload["regions"]
            if isinstance(region, dict)
        }
        self._rpp = {
            str(record["region_id"]): record
            for record in rpp_payload["records"]
            if isinstance(record, dict)
        }
        county_estimates_path = data_dir / "county_rpp_estimates.json"
        if county_estimates_path.exists():
            county_estimates_payload = json.loads(
                county_estimates_path.read_text(encoding="utf-8")
            )
            self._county_estimates = {
                str(record["county_fips"]): record
                for record in county_estimates_payload["records"]
                if isinstance(record, dict)
            }
        else:
            self._county_estimates = {}
        self._wages = {
            (str(record["region_id"]), str(record["soc_code"])): record
            for record in wages_payload["records"]
            if isinstance(record, dict)
        }
        county_features_payload = json.loads(
            (data_dir / "county_features.json").read_text(encoding="utf-8")
        )
        self._county_features = {
            str(record["county_fips"]): record
            for record in county_features_payload["records"]
            if isinstance(record, dict)
        }
        tax_rules_payload = json.loads(
            (data_dir / "state_income_tax_rules.json").read_text(encoding="utf-8")
        )
        tax_year = int(tax_rules_payload["tax_year"])
        self._state_tax_rules = {
            str(record["state_region_id"]): StateIncomeTaxRule(
                state_region_id=str(record["state_region_id"]),
                state_name=str(record["state_name"]),
                tax_year=tax_year,
                brackets=[
                    (Decimal(str(item["threshold"])), Decimal(str(item["rate"])))
                    for item in record["brackets"]
                ],
                standard_deduction=Decimal(str(record["standard_deduction"])),
                personal_exemption=Decimal(str(record["personal_exemption"])),
                standard_credit=Decimal(str(record["standard_credit"])),
                exemption_credit=Decimal(str(record["exemption_credit"])),
                no_wage_income_tax=bool(record["no_wage_income_tax"]),
                source_url=str(record["source_url"]),
            )
            for record in tax_rules_payload["records"]
            if isinstance(record, dict)
        }

    def resolve_rpp(self, region_id: str | None) -> RPPResolution:
        if region_id is None:
            return RPPResolution(
                requested_region_id=NATIONAL_REGION_ID,
                requested_region_name=NATIONAL_REGION_NAME,
                effective_region_id=NATIONAL_REGION_ID,
                effective_region_name=NATIONAL_REGION_NAME,
                year=max(int(record["year"]) for record in self._rpp.values()),
                source="official_bea",
                rpp_all_items=NATIONAL_RPP,
                rpp_housing=NATIONAL_RPP,
                rpp_goods=NATIONAL_RPP,
                rpp_utilities=NATIONAL_RPP,
                rpp_other_services=NATIONAL_RPP,
            )

        region = self._regions.get(region_id)
        if region is None:
            raise UnknownRegionError(region_id)
        effective_region_id = region_id
        record = self._rpp.get(effective_region_id)
        if record is None and region.get("type") == "county" and region.get("msa_id"):
            effective_region_id = str(region["msa_id"])
            record = self._rpp.get(effective_region_id)
        if record is None and region.get("type") == "county" and not region.get("msa_id"):
            estimate = self._county_estimates.get(str(region["fips"]))
            if estimate is not None:
                interval = estimate["confidence_interval"]["all_items"]
                return RPPResolution(
                    requested_region_id=region_id,
                    requested_region_name=str(region["name"]),
                    effective_region_id=region_id,
                    effective_region_name=str(region["name"]),
                    year=int(estimate["year"]),
                    source="modeled",
                    rpp_all_items=Decimal(str(estimate["predicted_rpp_all_items"])),
                    rpp_housing=Decimal(str(estimate["predicted_rpp_housing"])),
                    confidence_interval=(
                        Decimal(str(interval["lower"])),
                        Decimal(str(interval["upper"])),
                    ),
                    model_version=str(estimate["model_version"]),
                )
        if record is None:
            raise RPPUnavailableError(region_id)
        effective_region = self._regions.get(effective_region_id)
        if effective_region is None:
            raise RPPUnavailableError(region_id)
        return RPPResolution(
            requested_region_id=region_id,
            requested_region_name=str(region["name"]),
            effective_region_id=effective_region_id,
            effective_region_name=str(effective_region["name"]),
            year=int(record["year"]),
            source=str(record["source"]),
            rpp_all_items=Decimal(str(record["rpp_all_items"])),
            rpp_housing=self._decimal(record.get("rpp_housing")),
            rpp_goods=self._decimal(record.get("rpp_goods")),
            rpp_utilities=self._decimal(record.get("rpp_utilities")),
            rpp_other_services=self._decimal(record.get("rpp_other_services")),
        )

    def find_wage(self, region_id: str, soc_code: str) -> WageRecord | None:
        record = self._wages.get((region_id, soc_code))
        if record is None:
            return None
        return WageRecord.model_validate(record)

    def resolve_county_cost_profile(
        self, region_id: str | None
    ) -> CountyCostProfile | None:
        if region_id is None:
            return None
        region = self._regions.get(region_id)
        if region is None:
            raise UnknownRegionError(region_id)
        if region.get("type") != "county":
            return None
        record = self._county_features.get(str(region["fips"]))
        if record is None:
            return None
        metadata = record.get("source_metadata") or {}
        return CountyCostProfile(
            county_fips=str(record["county_fips"]),
            year=int(record["year"]),
            zori=self._decimal(record.get("zori")),
            hud_fmr_studio=Decimal(str(record["hud_fmr_studio"])),
            hud_fmr_1br=Decimal(str(record["hud_fmr_1br"])),
            hud_fmr_2br=Decimal(str(record["hud_fmr_2br"])),
            hud_fmr_3br=Decimal(str(record["hud_fmr_3br"])),
            zillow_observation=metadata.get("zillow_observation"),
            hud_fiscal_year=int(metadata["hud_fiscal_year"]),
        )

    def resolve_state_tax_rule(self, region_id: str | None) -> StateIncomeTaxRule | None:
        if region_id is None:
            return None
        region = self._regions.get(region_id)
        if region is None:
            raise UnknownRegionError(region_id)
        state_region_id = (
            region_id if region.get("type") == "state" else region.get("parent_region_id")
        )
        return self._state_tax_rules.get(str(state_region_id))

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        return None if value is None else Decimal(str(value))
