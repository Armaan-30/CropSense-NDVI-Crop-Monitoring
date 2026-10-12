"""System and diagnostics endpoints: health, configuration, Earth Engine test."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.api.dependencies import earth_engine_service
from app.core.config import Settings, get_settings
from app.core.logging_config import get_logger
from app.models.vegetation import (
    CALIBRATION_NOTE,
    GENERAL_LIMITATIONS,
    HEALTH_CLASSES,
    NDVI_PALETTE,
)
from app.schemas.common import CloudMaskMethod, CompositeMethod
from app.schemas.system import (
    ConfigResponse,
    EarthEngineStatus,
    GEETestResponse,
    HealthResponse,
)
from app.services.gee_service import GEEService
from app.services.metrics import utc_now_iso

logger = get_logger(__name__)

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and Earth Engine readiness",
)
def health(
    settings: Settings = Depends(get_settings),
    gee: GEEService = Depends(earth_engine_service),
) -> HealthResponse:
    """Report API liveness and whether Earth Engine is usable.

    Always returns HTTP 200 so an orchestrator does not evict an instance that
    is merely waiting on credentials. Read ``status``: ``"ok"`` means Earth
    Engine initialised, ``"degraded"`` means the API is up but analyses will
    fail - in which case ``earth_engine.remediation`` lists what to fix.

    This endpoint does not spend an Earth Engine round trip. Use
    ``/api/system/gee-test`` for a live connectivity check.
    """
    status_info = gee.status()
    earth_engine = EarthEngineStatus(**status_info)
    return HealthResponse(
        status="ok" if earth_engine.initialized else "degraded",
        app_name=settings.app_name,
        version=__version__,
        environment=settings.app_env,
        earth_engine=earth_engine,
        timestamp=utc_now_iso(),
    )


@router.get(
    "/api/system/config",
    response_model=ConfigResponse,
    summary="Non-sensitive server defaults",
)
def get_config(settings: Settings = Depends(get_settings)) -> ConfigResponse:
    """Expose server processing defaults so the UI can mirror them.

    Contains no credentials, no project ID and no service-account details.
    """
    return ConfigResponse(
        collection_id=settings.s2_collection_id,
        band_red=settings.band_red,
        band_nir=settings.band_nir,
        default_cloud_mask_method=CloudMaskMethod.CS_PLUS.value,
        default_composite_method=CompositeMethod.MEDIAN.value,
        default_scale_m=settings.default_analysis_scale_m,
        default_ndvi_class_thresholds=settings.ndvi_class_threshold_list,
        default_decline_threshold=settings.ndvi_decline_threshold,
        health_classes=[
            {
                "key": definition.key,
                "label": definition.label,
                "color": definition.color,
                "code": definition.code,
                "description": definition.description,
            }
            for definition in HEALTH_CLASSES
        ],
        ndvi_palette=list(NDVI_PALETTE),
        max_aoi_area_km2=settings.max_aoi_area_km2,
        max_date_range_days=settings.max_date_range_days,
        calibration_note=CALIBRATION_NOTE,
        limitations=list(GENERAL_LIMITATIONS),
    )


@router.get(
    "/api/system/gee-test",
    response_model=GEETestResponse,
    summary="Live Earth Engine connectivity test",
)
def gee_test(gee: GEEService = Depends(earth_engine_service)) -> GEETestResponse:
    """Execute a small real computation against Earth Engine.

    Verifies, in order: credentials load, ``ee.Initialize`` succeeds, a
    server-side computation round-trips, and the Sentinel-2 collection is
    queryable. Returns HTTP 200 with ``success=false`` and remediation steps on
    failure, so the response is always parseable by the dashboard.
    """
    result = gee.connectivity_test()
    if not result.get("success"):
        logger.warning("Earth Engine connectivity test failed: %s", result.get("message"))
    return GEETestResponse(**result)
