"""FastAPI application for Colculator's public calculation API."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException

from colculator.calculator.models import CalculationRequest, CalculationResponse
from colculator.calculator.repository import (
    CatalogRepository,
    RPPUnavailableError,
    UnknownRegionError,
)
from colculator.calculator.service import SalaryCalculator


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "frontend" / "public" / "data"

app = FastAPI(
    title="Colculator API",
    version="0.1.0",
    description=(
        "Source-transparent cost-of-living salary normalization using official "
        "BEA RPP and BLS OEWS data."
    ),
)


@lru_cache
def get_calculator() -> SalaryCalculator:
    data_dir = Path(os.environ.get("COLCULATOR_DATA_DIR", DEFAULT_DATA_DIR))
    return SalaryCalculator(CatalogRepository(data_dir))


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/v1/calculate",
    response_model=CalculationResponse,
    tags=["calculator"],
)
def calculate(
    request: CalculationRequest,
    calculator: SalaryCalculator = Depends(get_calculator),
) -> CalculationResponse:
    try:
        return calculator.calculate(request)
    except UnknownRegionError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_region", "region_id": str(error.args[0])},
        ) from error
    except RPPUnavailableError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "rpp_unavailable",
                "region_id": str(error.args[0]),
                "message": "No official or modeled RPP is available for this region.",
            },
        ) from error
