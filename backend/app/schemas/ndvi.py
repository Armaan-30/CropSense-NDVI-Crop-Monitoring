"""Schemas for the NDVI analysis endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.aoi import AOISummary, normalize_geojson
from app.schemas.common import (
    CloudMaskMethod,
    CompositeMethod,
    DateRange,
    HealthSummary,
    ImagerySummary,
    MapLayer,
    NDVIStatistics,
    TemporalAggregation,
)

_AOI_EXAMPLE: dict[str, Any] = {
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
}


class AnalysisOptions(BaseModel):
    """Optional per-request overrides for processing behaviour.

    Every field here has a server-side default from configuration. Sending
    ``options`` is never required.
    """

    model_config = ConfigDict(extra="forbid")

    cloud_mask_method: CloudMaskMethod | None = Field(
        None, description="Per-pixel cloud masking strategy. Server default: cs_plus."
    )
    composite_method: CompositeMethod | None = Field(
        None, description="How to reduce multiple scenes to one image. Server default: median."
    )
    scale_m: int | None = Field(
        None,
        ge=10,
        le=1000,
        description="Analysis scale in metres. 10 m is Sentinel-2 native for B4/B8.",
    )
    ndvi_class_thresholds: list[float] | None = Field(
        None,
        description=(
            "Exactly four ascending NDVI boundaries defining the five health classes. "
            "Overrides the server default. These are NOT universal - calibrate them "
            "for your crop, growth stage and region."
        ),
    )
    cloud_score_plus_threshold: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Cloud Score+ clearness cutoff; pixels below this are masked.",
    )
    include_true_color_layer: bool = Field(
        True, description="Also return an RGB layer for visual cross-checking."
    )

    @model_validator(mode="after")
    def _validate_thresholds(self) -> AnalysisOptions:
        thresholds = self.ndvi_class_thresholds
        if thresholds is None:
            return self
        if len(thresholds) != 4:
            raise ValueError(
                f"ndvi_class_thresholds must contain exactly 4 values (got {len(thresholds)})"
            )
        if thresholds != sorted(thresholds):
            raise ValueError("ndvi_class_thresholds must be in ascending order")
        if len(set(thresholds)) != 4:
            raise ValueError("ndvi_class_thresholds must be strictly increasing (no duplicates)")
        for value in thresholds:
            if not -1.0 <= value <= 1.0:
                raise ValueError(f"NDVI threshold {value} is outside the valid NDVI range [-1, 1]")
        return self


class _BaseAnalysisRequest(BaseModel):
    """Fields common to every AOI + date-window request."""

    model_config = ConfigDict(extra="forbid")

    aoi: dict[str, Any] = Field(
        ...,
        description=(
            "GeoJSON geometry, Feature, or single-feature FeatureCollection in "
            "EPSG:4326. Point geometries are buffered by `buffer_m`."
        ),
        json_schema_extra={"example": _AOI_EXAMPLE},
    )
    buffer_m: float = Field(
        250.0,
        ge=0.0,
        le=20_000.0,
        description="Buffer applied to Point AOIs to form a circular field, in metres.",
    )
    cloud_threshold: float = Field(
        30.0,
        ge=0.0,
        le=100.0,
        description=(
            "Scene-level maximum CLOUDY_PIXEL_PERCENTAGE. Scenes cloudier than this "
            "are discarded before per-pixel masking."
        ),
    )
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)

    @model_validator(mode="after")
    def _validate_aoi(self) -> _BaseAnalysisRequest:
        # Normalise early so a malformed AOI produces a 422 with a clear
        # message instead of an opaque Earth Engine error later on.
        self.aoi = normalize_geojson(self.aoi)
        return self


class NDVIAnalyzeRequest(_BaseAnalysisRequest):
    """Request body for ``POST /api/ndvi/analyze``."""

    start_date: date = Field(..., description="Window start (inclusive), YYYY-MM-DD.")
    end_date: date = Field(..., description="Window end (inclusive), YYYY-MM-DD.")

    @model_validator(mode="after")
    def _validate_dates(self) -> NDVIAnalyzeRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

    @property
    def date_range(self) -> DateRange:
        """The request window as a :class:`DateRange`."""
        return DateRange(start_date=self.start_date, end_date=self.end_date)


class NDVIAnalyzeResponse(BaseModel):
    """Full NDVI analysis result for one AOI and date window."""

    aoi: AOISummary
    imagery: ImagerySummary
    statistics: NDVIStatistics
    health: HealthSummary
    layers: list[MapLayer]
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal caveats, e.g. low valid-pixel fraction or a single-scene window.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Interpretation and limitation notes intended for display in the UI.",
    )
    computed_at: str = Field(..., description="Server UTC timestamp, ISO 8601.")
    duration_ms: int = Field(..., description="Server-side processing time in milliseconds.")


class TimeSeriesRequest(_BaseAnalysisRequest):
    """Request body for ``POST /api/ndvi/timeseries``."""

    start_date: date
    end_date: date
    aggregation: TemporalAggregation = Field(
        TemporalAggregation.SCENE,
        description=(
            "'scene' returns one point per usable overpass. The calendar options "
            "composite within each bin, which fills gaps at the cost of temporal precision."
        ),
    )
    min_valid_fraction: float = Field(
        0.10,
        ge=0.0,
        le=1.0,
        description=(
            "Drop time-series points whose cloud-free coverage of the AOI is below "
            "this fraction. Prevents a 2%-visible scene from creating a fake dip."
        ),
    )

    @model_validator(mode="after")
    def _validate_dates(self) -> TimeSeriesRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class TimeSeriesPoint(BaseModel):
    """One NDVI observation (single scene or composited bin) over the AOI."""

    date: str = Field(..., description="Representative date of the observation (UTC, ISO 8601).")
    mean_ndvi: float | None = None
    min_ndvi: float | None = None
    max_ndvi: float | None = None
    median_ndvi: float | None = None
    std_dev_ndvi: float | None = None
    valid_pixel_fraction: float | None = Field(
        None, description="Fraction of the AOI that was cloud-free for this observation."
    )
    scene_count: int = Field(1, description="Scenes contributing to this point.")
    scene_cloud_percent: float | None = Field(
        None, description="Scene-level cloud percentage (single-scene points only)."
    )
    scene_id: str | None = None


class TrendSummary(BaseModel):
    """Ordinary-least-squares trend fitted to the retained time-series points.

    Computed on the server from the points returned in this response, so it is
    fully reproducible. With few points, a wide observation gap, or a strong
    phenological cycle in the window, a linear trend can be misleading -
    always read it alongside the chart.
    """

    n_points: int
    slope_ndvi_per_day: float | None = None
    slope_ndvi_per_30_days: float | None = None
    intercept: float | None = None
    r_squared: float | None = Field(
        None, description="Coefficient of determination of the linear fit, 0-1."
    )
    direction: str = Field(
        ..., description="'increasing', 'decreasing', 'stable', or 'insufficient_data'."
    )
    first_value: float | None = None
    last_value: float | None = None
    absolute_change: float | None = Field(
        None, description="last_value - first_value in NDVI units."
    )
    interpretation: str = Field(
        ..., description="Plain-language reading of the trend, with its caveats."
    )


class TimeSeriesResponse(BaseModel):
    """NDVI time series and trend for one AOI."""

    aoi: AOISummary
    collection_id: str
    requested_range: DateRange
    aggregation: TemporalAggregation
    cloud_threshold_percent: float
    cloud_mask_method: CloudMaskMethod
    scale_m: int
    points: list[TimeSeriesPoint]
    excluded_point_count: int = Field(
        0, description="Observations dropped for falling below min_valid_fraction."
    )
    trend: TrendSummary
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    computed_at: str
    duration_ms: int


class ChangeDetectionRequest(_BaseAnalysisRequest):
    """Request body for ``POST /api/ndvi/change``.

    Compares a baseline window against a recent window over the same AOI.
    Both windows are composited independently, then differenced per pixel.
    """

    baseline_start_date: date
    baseline_end_date: date
    recent_start_date: date
    recent_end_date: date
    decline_threshold: float | None = Field(
        None,
        gt=0.0,
        le=2.0,
        description=(
            "Minimum NDVI drop (baseline minus recent) that flags a pixel as a "
            "potential stress area. Server default: 0.15. Screening only - not a diagnosis."
        ),
    )

    @model_validator(mode="after")
    def _validate_windows(self) -> ChangeDetectionRequest:
        if self.baseline_end_date < self.baseline_start_date:
            raise ValueError("baseline_end_date must be on or after baseline_start_date")
        if self.recent_end_date < self.recent_start_date:
            raise ValueError("recent_end_date must be on or after recent_start_date")
        if self.recent_start_date < self.baseline_start_date:
            raise ValueError(
                "recent window must start on or after the baseline window "
                "(baseline is the earlier reference period)"
            )
        return self

    @property
    def baseline_range(self) -> DateRange:
        return DateRange(start_date=self.baseline_start_date, end_date=self.baseline_end_date)

    @property
    def recent_range(self) -> DateRange:
        return DateRange(start_date=self.recent_start_date, end_date=self.recent_end_date)


class ChangeStatistics(BaseModel):
    """Statistics of the per-pixel NDVI difference (recent minus baseline)."""

    mean_change: float | None = None
    min_change: float | None = None
    max_change: float | None = None
    median_change: float | None = None
    std_dev_change: float | None = None
    comparable_area_ha: float = Field(
        ..., description="Area cloud-free in BOTH windows, and therefore comparable."
    )
    comparable_area_fraction: float | None = Field(
        None, ge=0.0, le=1.0, description="comparable_area_ha / AOI area."
    )
    declined_area_ha: float = Field(
        ..., description="Comparable area whose NDVI dropped by >= decline_threshold."
    )
    declined_percent_of_comparable: float = Field(
        ..., description="declined_area_ha as a share of comparable area, 0-100."
    )
    improved_area_ha: float = Field(
        ..., description="Comparable area whose NDVI rose by >= decline_threshold."
    )
    improved_percent_of_comparable: float = Field(..., description="0-100.")
    decline_threshold: float


class ChangeDetectionResponse(BaseModel):
    """Two-period NDVI comparison and stress screening result."""

    aoi: AOISummary
    baseline_imagery: ImagerySummary
    recent_imagery: ImagerySummary
    baseline_statistics: NDVIStatistics
    recent_statistics: NDVIStatistics
    baseline_health: HealthSummary
    recent_health: HealthSummary
    change: ChangeStatistics
    layers: list[MapLayer]
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    computed_at: str
    duration_ms: int
