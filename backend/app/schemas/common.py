"""Shared enums and schemas used across CropSense endpoints."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class CloudMaskMethod(StrEnum):
    """Available per-pixel cloud/shadow masking strategies.

    - ``cs_plus``: Google Cloud Score+ (``GOOGLE/CLOUD_SCORE_PLUS``). Currently
      the best-performing general-purpose Sentinel-2 cloud/shadow mask and the
      recommended default.
    - ``scl``: Sen2Cor Scene Classification Layer shipped with L2A. Masks
      cloud (medium/high probability), cirrus, cloud shadow, and saturated
      pixels. No extra collection join required.
    - ``qa60``: Legacy 60 m QA bitmask (opaque + cirrus bits only). Coarse and
      known to miss shadows; kept for reproducing older analyses.
    - ``none``: No pixel masking. Scene-level ``CLOUDY_PIXEL_PERCENTAGE``
      filtering still applies. Diagnostic use only.
    """

    CS_PLUS = "cs_plus"
    SCL = "scl"
    QA60 = "qa60"
    NONE = "none"


class CompositeMethod(StrEnum):
    """How multiple cloud-masked scenes are reduced to one image.

    - ``median``: Per-pixel median. Robust to residual cloud and the safe
      default for multi-scene windows.
    - ``mean``: Per-pixel mean. Smoother but sensitive to unmasked cloud.
    - ``greenest``: Per-pixel maximum NDVI ("greenest pixel"). Useful for
      peak-vigour mapping; biased high, so it is a poor choice for absolute
      stress assessment.
    - ``most_recent``: The latest scene's value wherever it is unmasked,
      falling back to older scenes underneath. Best for "current state".
    """

    MEDIAN = "median"
    MEAN = "mean"
    GREENEST = "greenest"
    MOST_RECENT = "most_recent"


class TemporalAggregation(StrEnum):
    """Time-step used to build an NDVI time series."""

    SCENE = "scene"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class DateRange(BaseModel):
    """An inclusive-start / inclusive-end calendar date window.

    Earth Engine's ``filterDate`` end bound is exclusive, so the service layer
    adds one day when converting. Keeping the API inclusive matches how users
    read a date picker.
    """

    start_date: date = Field(..., description="First day of the window (inclusive).")
    end_date: date = Field(..., description="Last day of the window (inclusive).")

    @model_validator(mode="after")
    def _validate_order(self) -> DateRange:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

    @property
    def days(self) -> int:
        """Length of the window in days (inclusive of both bounds)."""
        return (self.end_date - self.start_date).days + 1


class LegendStop(BaseModel):
    """One entry in a map-layer legend."""

    label: str
    color: str = Field(..., description="CSS hex colour, e.g. '#1a9850'.")
    value_min: float | None = Field(None, description="Lower bound of the bin, if applicable.")
    value_max: float | None = Field(None, description="Upper bound of the bin, if applicable.")


class MapLayer(BaseModel):
    """A ready-to-render Earth Engine raster tile layer.

    ``tile_url_template`` is a short-lived, signed Earth Engine tile endpoint
    produced by ``ee.Image.getMapId()``. It carries no service-account key, so
    it is safe to hand to a browser. It is *not* permanent - treat it as
    valid for the current session and re-request on expiry.
    """

    id: str = Field(..., description="Stable layer identifier, e.g. 'ndvi'.")
    name: str = Field(..., description="Human-readable layer name.")
    description: str = Field("", description="What the layer shows and how to read it.")
    tile_url_template: str = Field(
        ...,
        description="XYZ tile template with {x}, {y}, {z} placeholders.",
    )
    attribution: str = Field(
        "Contains modified Copernicus Sentinel data, processed via Google Earth Engine.",
        description="Required data attribution for display on the map.",
    )
    opacity: float = Field(1.0, ge=0.0, le=1.0)
    legend: list[LegendStop] = Field(default_factory=list)
    value_range: list[float] | None = Field(
        None, description="[min, max] of the stretched value range, when continuous."
    )


class NDVIStatistics(BaseModel):
    """Zonal NDVI statistics over the AOI.

    All values are computed by Earth Engine over *unmasked* (cloud-free)
    pixels only. ``valid_pixel_count`` and ``valid_pixel_fraction`` tell you
    how much of the AOI actually contributed - a mean built from 3% of the
    field is not a field mean.
    """

    mean: float | None = None
    min: float | None = None
    max: float | None = None
    median: float | None = None
    std_dev: float | None = None
    p10: float | None = Field(None, description="10th percentile of NDVI.")
    p90: float | None = Field(None, description="90th percentile of NDVI.")
    valid_pixel_count: int | None = Field(
        None, description="Cloud-free pixels that contributed to these statistics."
    )
    total_pixel_count: int | None = Field(
        None, description="Pixels intersecting the AOI at the analysis scale."
    )
    valid_pixel_fraction: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="valid_pixel_count / total_pixel_count. Low values mean low confidence.",
    )
    scale_m: int | None = Field(None, description="Analysis scale in metres.")


class HealthClassStat(BaseModel):
    """Area and share of the AOI falling in one NDVI health class."""

    key: str = Field(..., description="Machine key, e.g. 'healthy'.")
    label: str = Field(..., description="Display label, e.g. 'Healthy'.")
    color: str = Field(..., description="CSS hex colour used on the map and in charts.")
    ndvi_min: float | None = Field(None, description="Inclusive lower NDVI bound (null = -1).")
    ndvi_max: float | None = Field(None, description="Exclusive upper NDVI bound (null = +1).")
    area_ha: float = Field(..., description="Area in hectares.")
    percent_of_valid: float = Field(..., description="Share of cloud-free classified area, 0-100.")
    pixel_count: int = Field(..., description="Number of contributing pixels.")


class HealthSummary(BaseModel):
    """NDVI health classification result for one image/composite."""

    thresholds: list[float] = Field(
        ...,
        description="The four NDVI class boundaries actually used for this request.",
    )
    thresholds_source: str = Field(
        ...,
        description="'request' if the client overrode them, otherwise 'server_default'.",
    )
    classes: list[HealthClassStat]
    dominant_class: str | None = Field(
        None, description="Key of the class covering the largest area."
    )
    classified_area_ha: float = Field(
        ..., description="Total cloud-free area that was classified, in hectares."
    )
    calibration_note: str = Field(
        ...,
        description="Mandatory caveat that thresholds are generic and need local calibration.",
    )


class ImagerySummary(BaseModel):
    """Provenance of the imagery behind a result.

    Every number CropSense reports is traceable to these scenes. If
    ``scene_count`` is 1 the composite is a single overpass; if it is 0 the
    request should have failed with ``no_imagery``.
    """

    collection_id: str
    scene_count: int
    scene_dates: list[str] = Field(
        default_factory=list, description="Acquisition dates (UTC) of contributing scenes."
    )
    scene_ids: list[str] = Field(
        default_factory=list, description="Earth Engine asset IDs of contributing scenes."
    )
    first_scene_date: str | None = None
    last_scene_date: str | None = None
    mean_scene_cloud_percent: float | None = Field(
        None, description="Mean CLOUDY_PIXEL_PERCENTAGE across contributing scenes."
    )
    cloud_threshold_percent: float
    cloud_mask_method: CloudMaskMethod
    composite_method: CompositeMethod
    requested_range: DateRange


class ErrorResponse(BaseModel):
    """Uniform error envelope returned for every non-2xx response."""

    code: str = Field(..., description="Stable machine-readable error code.")
    message: str = Field(..., description="Human-readable explanation.")
    details: dict[str, Any] = Field(default_factory=dict)
