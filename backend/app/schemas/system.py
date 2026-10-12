"""Schemas for system / meta endpoints (health check, configuration echo)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EarthEngineStatus(BaseModel):
    """Reported state of the Earth Engine connection.

    ``initialized`` reflects whether ``ee.Initialize`` succeeded. ``reachable``
    is only True after a real round-trip computation has been executed against
    Earth Engine servers, so it distinguishes "library loaded" from "we can
    actually run analyses".
    """

    initialized: bool
    reachable: bool | None = Field(
        None,
        description="True if a live round-trip test succeeded. None if not tested.",
    )
    auth_method: str | None = Field(
        None, description="'service_account', 'local_credentials', or None."
    )
    project: str | None = Field(None, description="Google Cloud project used for Earth Engine.")
    service_account_email: str | None = None
    high_volume_endpoint: bool | None = None
    error: str | None = Field(None, description="Why Earth Engine is unavailable, if it is.")
    remediation: list[str] = Field(
        default_factory=list,
        description="Concrete operator steps to fix an unavailable Earth Engine connection.",
    )


class HealthResponse(BaseModel):
    """Response for ``GET /health``.

    ``status`` is ``"ok"`` when the API and Earth Engine are both usable, and
    ``"degraded"`` when the API is up but Earth Engine is not. The HTTP status
    stays 200 in both cases so load balancers do not remove an instance that is
    merely waiting on credentials; check the body.
    """

    status: str = Field(..., description="'ok' or 'degraded'.")
    app_name: str
    version: str
    environment: str
    earth_engine: EarthEngineStatus
    timestamp: str = Field(..., description="Server UTC time, ISO 8601.")


class ConfigResponse(BaseModel):
    """Non-sensitive server configuration, so the UI can mirror server defaults.

    Deliberately excludes every credential-bearing field.
    """

    collection_id: str
    band_red: str
    band_nir: str
    default_cloud_mask_method: str
    default_composite_method: str
    default_scale_m: int
    default_ndvi_class_thresholds: list[float]
    default_decline_threshold: float
    health_classes: list[dict[str, Any]]
    ndvi_palette: list[str]
    max_aoi_area_km2: float
    max_date_range_days: int
    calibration_note: str
    limitations: list[str]


class GEETestResponse(BaseModel):
    """Response for ``GET /api/system/gee-test``.

    Executes a small but real Earth Engine computation. If this returns
    ``success=True``, credentials, project registration and network egress are
    all working.
    """

    success: bool
    auth_method: str | None = None
    project: str | None = None
    round_trip_ms: int | None = None
    server_side_number: float | None = Field(
        None, description="Result of a trivial ee.Number computation evaluated server-side."
    )
    sample_collection_id: str | None = None
    sample_scene_count: int | None = Field(
        None, description="Sentinel-2 scenes found by a small bounded test query."
    )
    sample_scene_id: str | None = None
    message: str
    remediation: list[str] = Field(default_factory=list)
