"""Read-only repository over the committed official-data artifacts."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from .models import RPPResolution, WageRecord


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
        self._wages = {
            (str(record["region_id"]), str(record["soc_code"])): record
            for record in wages_payload["records"]
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

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        return None if value is None else Decimal(str(value))
