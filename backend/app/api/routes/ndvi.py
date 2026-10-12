"""NDVI analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from app.api.dependencies import analysis_history_store, analysis_service
from app.core.logging_config import get_logger
from app.schemas.common import ErrorResponse
from app.schemas.ndvi import (
    ChangeDetectionRequest,
    ChangeDetectionResponse,
    NDVIAnalyzeRequest,
    NDVIAnalyzeResponse,
    TimeSeriesRequest,
    TimeSeriesResponse,
)
from app.services.analysis_service import AnalysisService
from app.services.history_store import AnalysisHistoryStore

logger = get_logger(__name__)

router = APIRouter(prefix="/ndvi", tags=["ndvi"])

# Shared OpenAPI error documentation.
_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "No Sentinel-2 imagery matched the filters."},
    422: {"model": ErrorResponse, "description": "Invalid AOI, date window, or parameters."},
    502: {"model": ErrorResponse, "description": "Earth Engine failed to compute the request."},
    503: {
        "model": ErrorResponse,
        "description": "Earth Engine is not authenticated or not configured.",
    },
}

_ANALYZE_EXAMPLE = {
    "aoi": {
        "type": "Polygon",
        "coordinates": [
            [
                [75.8000, 30.9000],
                [75.8120, 30.9000],
                [75.8120, 30.9080],
                [75.8000, 30.9080],
                [75.8000, 30.9000],
            ]
        ],
    },
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "cloud_threshold": 30,
    "options": {"cloud_mask_method": "cs_plus", "composite_method": "median"},
}


@router.post(
    "/analyze",
    response_model=NDVIAnalyzeResponse,
    responses=_ERROR_RESPONSES,
    summary="Analyse NDVI and crop health for an AOI over a date window",
)
def analyze_ndvi(
    request: NDVIAnalyzeRequest = Body(
        ...,
        # `openapi_examples` (not `examples`) is the named-example form; it maps
        # to the OpenAPI 3.1 Example Object so /docs shows a labelled dropdown.
        openapi_examples={
            "punjab_field": {
                "summary": "~10 ha field, one month, moderate cloud tolerance",
                "value": _ANALYZE_EXAMPLE,
            }
        },
    ),
    service: AnalysisService = Depends(analysis_service),
    history: AnalysisHistoryStore = Depends(analysis_history_store),
) -> NDVIAnalyzeResponse:
    """Compute NDVI, zonal statistics, health classes and map layers.

    Pipeline: filter Sentinel-2 L2A by AOI, date and scene cloud cover -> mask
    cloud/shadow per pixel -> composite -> ``NDVI = (B8 - B4) / (B8 + B4)`` ->
    reduce statistics over the AOI -> classify into five health categories ->
    register signed tile URLs.

    Read the ``warnings`` array before trusting the numbers: it reports low
    cloud-free coverage, single-scene composites and other reliability caveats.
    """
    logger.info(
        "POST /ndvi/analyze: %s to %s, cloud<=%s%%, geometry=%s",
        request.start_date,
        request.end_date,
        request.cloud_threshold,
        request.aoi.get("type"),
    )
    result = service.analyze(request)
    _persist_history(history, "snapshot", request, result)
    return result


@router.post(
    "/timeseries",
    response_model=TimeSeriesResponse,
    responses=_ERROR_RESPONSES,
    summary="NDVI time series and linear trend for an AOI",
)
def ndvi_timeseries(
    request: TimeSeriesRequest,
    service: AnalysisService = Depends(analysis_service),
    history: AnalysisHistoryStore = Depends(analysis_history_store),
) -> TimeSeriesResponse:
    """Return mean NDVI over time plus an ordinary-least-squares trend.

    ``aggregation='scene'`` gives one point per usable overpass; the calendar
    options composite within each bin to fill cloud gaps. Observations covering
    less than ``min_valid_fraction`` of the AOI are dropped and counted in
    ``excluded_point_count``.
    """
    logger.info(
        "POST /ndvi/timeseries: %s to %s, aggregation=%s",
        request.start_date,
        request.end_date,
        request.aggregation.value,
    )
    result = service.time_series(request)
    _persist_history(history, "series", request, result)
    return result


@router.post(
    "/change",
    response_model=ChangeDetectionResponse,
    responses=_ERROR_RESPONSES,
    summary="Compare two periods and flag potential vegetation stress",
)
def ndvi_change(
    request: ChangeDetectionRequest,
    service: AnalysisService = Depends(analysis_service),
    history: AnalysisHistoryStore = Depends(analysis_history_store),
) -> ChangeDetectionResponse:
    """Difference two composited windows and screen for significant decline.

    Only pixels cloud-free in both windows are compared. Flagged areas indicate
    **potential** vegetation stress requiring ground verification - NDVI cannot
    identify a cause and does not diagnose crop disease.
    """
    logger.info(
        "POST /ndvi/change: baseline %s..%s vs recent %s..%s",
        request.baseline_start_date,
        request.baseline_end_date,
        request.recent_start_date,
        request.recent_end_date,
    )
    result = service.detect_change(request)
    _persist_history(history, "compare", request, result)
    return result


def _persist_history(
    history: AnalysisHistoryStore,
    mode: str,
    request: BaseModel,
    result: BaseModel,
) -> None:
    """Persist successful results without turning a storage fault into API downtime."""
    try:
        history.save(
            mode=mode,
            request=request.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
        )
    except Exception:
        logger.exception("Analysis succeeded but local history persistence failed")
        warnings = getattr(result, "warnings", None)
        if isinstance(warnings, list):
            warnings.append("Analysis completed, but it could not be saved to local history.")
