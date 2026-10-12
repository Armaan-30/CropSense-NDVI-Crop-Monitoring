"""Pure-Python analytics: statistics parsing, area maths, trend fitting, warnings.

Deliberately free of any ``ee`` import. Everything here operates on plain
dicts and floats that Earth Engine has already returned, which makes this - the
part most likely to contain arithmetic bugs - unit-testable without credentials
or network access.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from app.core.logging_config import get_logger
from app.models.vegetation import (
    CALIBRATION_NOTE,
    HEALTH_CLASSES,
    resolve_class_bounds,
)
from app.schemas.common import (
    HealthClassStat,
    HealthSummary,
    NDVIStatistics,
)
from app.schemas.ndvi import TimeSeriesPoint, TrendSummary

logger = get_logger(__name__)

M2_PER_HECTARE = 10_000.0

# |slope| below this (in NDVI units per 30 days) is reported as "stable".
# Chosen to sit above typical inter-scene noise from residual atmospheric
# effects and viewing-geometry differences, not derived from a validation study.
TREND_STABLE_BAND_PER_30D = 0.02

# Below this cloud-free coverage of the AOI, aggregate statistics are reported
# but flagged as low confidence.
LOW_VALID_FRACTION = 0.40

# Minimum points before a linear trend is worth reporting at all.
MIN_TREND_POINTS = 3


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def epoch_ms_to_iso(timestamp_ms: float | int | None) -> str | None:
    """Convert an Earth Engine ``system:time_start`` value to an ISO-8601 string.

    Args:
        timestamp_ms: Milliseconds since the Unix epoch (UTC), or None.

    Returns:
        An ISO-8601 UTC timestamp, or None if the input was None.
    """
    if timestamp_ms is None:
        return None
    try:
        moment = datetime.fromtimestamp(float(timestamp_ms) / 1000.0, tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        logger.warning("Unparseable Earth Engine timestamp: %r", timestamp_ms)
        return None
    return moment.isoformat().replace("+00:00", "Z")


def epoch_ms_to_date_str(timestamp_ms: float | int | None) -> str | None:
    """Convert ``system:time_start`` to a ``YYYY-MM-DD`` UTC date string."""
    iso = epoch_ms_to_iso(timestamp_ms)
    return iso.split("T")[0] if iso else None


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string with a ``Z`` suffix."""
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Zonal statistics
# ---------------------------------------------------------------------------
def _first_float(raw: dict[str, Any], *keys: str) -> float | None:
    """Return the first present, finite, non-null value among ``keys``."""
    for key in keys:
        if key in raw and raw[key] is not None:
            try:
                value = float(raw[key])
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                return value
    return None


def parse_zonal_statistics(
    raw: dict[str, Any] | None,
    *,
    band: str,
    scale_m: int,
    valid_area_m2: float | None = None,
    aoi_area_m2: float | None = None,
) -> NDVIStatistics:
    """Turn a combined-reducer ``reduceRegion`` result into typed statistics.

    Earth Engine names combined-reducer outputs ``<band>_<reducer>`` (e.g.
    ``NDVI_mean``, ``NDVI_p50``). When a region is fully masked, every value
    comes back as ``None`` rather than as an error - that is a real result
    meaning "no cloud-free pixels here", and it is preserved as None rather
    than coerced to 0.

    Args:
        raw: The evaluated ``reduceRegion`` dictionary, or None.
        band: Band name used as the key prefix.
        scale_m: Analysis scale, echoed into the result.
        valid_area_m2: Cloud-free area within the AOI.
        aoi_area_m2: Total AOI area, used for the valid fraction.

    Returns:
        Populated :class:`NDVIStatistics`.
    """
    raw = raw or {}
    prefix = band

    valid_fraction: float | None = None
    if valid_area_m2 is not None and aoi_area_m2 and aoi_area_m2 > 0:
        valid_fraction = min(max(valid_area_m2 / aoi_area_m2, 0.0), 1.0)

    count = _first_float(raw, f"{prefix}_count", "count")
    total_pixels: int | None = None
    if aoi_area_m2 and scale_m > 0:
        total_pixels = round(aoi_area_m2 / (scale_m * scale_m))

    return NDVIStatistics(
        mean=_round_opt(_first_float(raw, f"{prefix}_mean", "mean")),
        min=_round_opt(_first_float(raw, f"{prefix}_min", "min")),
        max=_round_opt(_first_float(raw, f"{prefix}_max", "max")),
        median=_round_opt(_first_float(raw, f"{prefix}_p50", "p50", f"{prefix}_median")),
        std_dev=_round_opt(_first_float(raw, f"{prefix}_stdDev", "stdDev")),
        p10=_round_opt(_first_float(raw, f"{prefix}_p10", "p10")),
        p90=_round_opt(_first_float(raw, f"{prefix}_p90", "p90")),
        valid_pixel_count=int(count) if count is not None else None,
        total_pixel_count=total_pixels,
        valid_pixel_fraction=_round_opt(valid_fraction, digits=4),
        scale_m=scale_m,
    )


def _round_opt(value: float | None, *, digits: int = 4) -> float | None:
    """Round a value if it is present, otherwise pass None through."""
    return None if value is None else round(value, digits)


# ---------------------------------------------------------------------------
# Health classification summary
# ---------------------------------------------------------------------------
def build_health_summary(
    grouped_areas: dict[str, Any] | None,
    *,
    thresholds: Sequence[float],
    thresholds_source: str,
) -> HealthSummary:
    """Convert grouped per-class areas into a :class:`HealthSummary`.

    ``grouped_areas`` is the evaluated result of a grouped ``reduceRegion``,
    shaped as ``{"groups": [{"class": 3, "sum": 12345.6, "count": 123}, ...]}``.
    Classes absent from the result had zero area and are emitted with zeros so
    the dashboard always renders all five categories.

    Percentages are computed against the *classified* (cloud-free) area, not the
    AOI area, so they always sum to 100 and are never diluted by cloud gaps.

    Args:
        grouped_areas: Evaluated grouped reduction, or None.
        thresholds: The four NDVI boundaries that were used.
        thresholds_source: ``'request'`` or ``'server_default'``.

    Returns:
        A fully populated :class:`HealthSummary`.
    """
    groups = (grouped_areas or {}).get("groups") or []

    area_by_code: dict[int, float] = {}
    pixels_by_code: dict[int, int] = {}
    for group in groups:
        try:
            code = int(group["class"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Skipping malformed health-class group: %r", group)
            continue
        area_by_code[code] = float(group.get("sum") or 0.0)
        pixels_by_code[code] = round(float(group.get("count") or 0.0))

    total_area_m2 = sum(area_by_code.values())

    class_stats: list[HealthClassStat] = []
    for definition, lower, upper in resolve_class_bounds(list(thresholds)):
        area_m2 = area_by_code.get(definition.code, 0.0)
        percent = (area_m2 / total_area_m2 * 100.0) if total_area_m2 > 0 else 0.0
        class_stats.append(
            HealthClassStat(
                key=definition.key,
                label=definition.label,
                color=definition.color,
                ndvi_min=lower,
                ndvi_max=upper,
                area_ha=round(area_m2 / M2_PER_HECTARE, 4),
                percent_of_valid=round(percent, 2),
                pixel_count=pixels_by_code.get(definition.code, 0),
            )
        )

    dominant = max(class_stats, key=lambda stat: stat.area_ha) if class_stats else None
    dominant_key = dominant.key if dominant and dominant.area_ha > 0 else None

    return HealthSummary(
        thresholds=[float(value) for value in thresholds],
        thresholds_source=thresholds_source,
        classes=class_stats,
        dominant_class=dominant_key,
        classified_area_ha=round(total_area_m2 / M2_PER_HECTARE, 4),
        calibration_note=CALIBRATION_NOTE,
    )


# ---------------------------------------------------------------------------
# Trend fitting
# ---------------------------------------------------------------------------
def fit_linear_trend(points: Sequence[TimeSeriesPoint]) -> TrendSummary:
    """Fit an ordinary-least-squares line to a mean-NDVI time series.

    The independent variable is days elapsed since the first retained
    observation, so the slope is directly interpretable as NDVI units per day.

    Deliberate limitations, stated in the returned ``interpretation``:

    * A straight line is a poor model of a crop's phenological curve. Over a
      full season NDVI rises then falls, and a linear fit through both limbs can
      report "stable" for a field that grew and was then harvested.
    * Sentinel-2 observations are irregularly spaced because of cloud, so points
      are not evenly weighted in time.
    * No significance test is performed and no confidence interval is reported.

    Args:
        points: Time-series points, ascending by date.

    Returns:
        A :class:`TrendSummary`. With fewer than :data:`MIN_TREND_POINTS` usable
        points, ``direction`` is ``'insufficient_data'`` and the coefficients
        are None.
    """
    usable = [
        point
        for point in points
        if point.mean_ndvi is not None and _parse_iso_date(point.date) is not None
    ]

    if len(usable) < MIN_TREND_POINTS:
        return TrendSummary(
            n_points=len(usable),
            direction="insufficient_data",
            first_value=usable[0].mean_ndvi if usable else None,
            last_value=usable[-1].mean_ndvi if usable else None,
            absolute_change=(
                round(usable[-1].mean_ndvi - usable[0].mean_ndvi, 4)
                if len(usable) >= 2
                and usable[0].mean_ndvi is not None
                and usable[-1].mean_ndvi is not None
                else None
            ),
            interpretation=(
                f"Only {len(usable)} cloud-free observation(s) were available, which is "
                f"too few to fit a trend (minimum {MIN_TREND_POINTS}). Widen the date "
                "range or raise the cloud-cover limit."
            ),
        )

    origin = _parse_iso_date(usable[0].date)
    assert origin is not None  # guaranteed by the filter above

    xs: list[float] = []
    ys: list[float] = []
    for point in usable:
        moment = _parse_iso_date(point.date)
        if moment is None:  # pragma: no cover - filtered above
            continue
        xs.append((moment - origin).total_seconds() / 86400.0)
        ys.append(float(point.mean_ndvi))  # type: ignore[arg-type]

    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))

    if sxx == 0:
        # Every observation shares one date; a slope is undefined.
        return TrendSummary(
            n_points=n,
            direction="insufficient_data",
            first_value=round(ys[0], 4),
            last_value=round(ys[-1], 4),
            absolute_change=round(ys[-1] - ys[0], 4),
            interpretation=(
                "All observations fall on the same date, so no time trend can be estimated."
            ),
        )

    slope_per_day = sxy / sxx
    intercept = mean_y - slope_per_day * mean_x
    slope_per_30d = slope_per_day * 30.0
    r_squared = (sxy * sxy) / (sxx * syy) if syy > 0 else 0.0

    if abs(slope_per_30d) < TREND_STABLE_BAND_PER_30D:
        direction = "stable"
    elif slope_per_30d > 0:
        direction = "increasing"
    else:
        direction = "decreasing"

    span_days = max(xs) - min(xs)
    interpretation = _describe_trend(
        direction=direction,
        slope_per_30d=slope_per_30d,
        r_squared=r_squared,
        n_points=n,
        span_days=span_days,
    )

    return TrendSummary(
        n_points=n,
        slope_ndvi_per_day=round(slope_per_day, 6),
        slope_ndvi_per_30_days=round(slope_per_30d, 4),
        intercept=round(intercept, 4),
        r_squared=round(max(min(r_squared, 1.0), 0.0), 4),
        direction=direction,
        first_value=round(ys[0], 4),
        last_value=round(ys[-1], 4),
        absolute_change=round(ys[-1] - ys[0], 4),
        interpretation=interpretation,
    )


def _describe_trend(
    *,
    direction: str,
    slope_per_30d: float,
    r_squared: float,
    n_points: int,
    span_days: float,
) -> str:
    """Compose the plain-language trend reading, including its caveats."""
    if direction == "stable":
        headline = (
            f"Mean NDVI is broadly stable over the window "
            f"({slope_per_30d:+.3f} per 30 days, within the +/-"
            f"{TREND_STABLE_BAND_PER_30D:.2f} noise band)."
        )
    elif direction == "increasing":
        headline = (
            f"Mean NDVI is increasing at about {slope_per_30d:+.3f} NDVI units per "
            "30 days, consistent with canopy development or recovery."
        )
    else:
        headline = (
            f"Mean NDVI is decreasing at about {slope_per_30d:+.3f} NDVI units per "
            "30 days. This is consistent with senescence, harvest, or developing "
            "stress - NDVI alone cannot distinguish between them."
        )

    fit_quality = (
        f"Linear fit R-squared is {r_squared:.2f} over {n_points} observations spanning "
        f"{span_days:.0f} days."
    )

    if r_squared < 0.3:
        fit_quality += (
            " The low R-squared means a straight line explains little of the variation; "
            "read the chart rather than the slope."
        )
    if span_days > 150:
        fit_quality += (
            " Over a window this long a crop's NDVI typically rises then falls, so a "
            "single linear slope can be misleading."
        )

    return f"{headline} {fit_quality}"


def _parse_iso_date(value: str | None) -> datetime | None:
    """Parse an ISO-8601 date or datetime string into an aware UTC datetime."""
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        try:
            moment = datetime.fromisoformat(text.split("T")[0])
        except ValueError:
            logger.warning("Unparseable time-series date: %r", value)
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment


# ---------------------------------------------------------------------------
# Area maths
# ---------------------------------------------------------------------------
def m2_to_ha(area_m2: float | None) -> float:
    """Convert square metres to hectares, treating None as zero."""
    return round((area_m2 or 0.0) / M2_PER_HECTARE, 4)


def safe_percent(numerator: float | None, denominator: float | None) -> float:
    """Percentage of ``numerator`` in ``denominator``, 0.0 when undefined."""
    if not denominator:
        return 0.0
    return round((numerator or 0.0) / denominator * 100.0, 2)


def mean_or_none(values: Iterable[float | int | None]) -> float | None:
    """Arithmetic mean of the non-None values, or None if there are none."""
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 3)


# ---------------------------------------------------------------------------
# Warning generation
# ---------------------------------------------------------------------------
def build_quality_warnings(
    *,
    scene_count: int,
    statistics: NDVIStatistics,
    cloud_threshold: float,
    window_days: int,
) -> list[str]:
    """Generate honest, specific caveats about a result's reliability.

    These are surfaced in the dashboard so a user cannot mistake a composite
    built from one 15%-visible scene for a confident field measurement.
    """
    warnings: list[str] = []

    if scene_count == 1:
        warnings.append(
            "Only one Sentinel-2 scene met the filters, so the result is a single "
            "overpass rather than a cloud-robust composite. Residual haze or thin "
            "cirrus in that scene will bias NDVI downward."
        )

    fraction = statistics.valid_pixel_fraction
    if fraction is not None and fraction < LOW_VALID_FRACTION:
        warnings.append(
            f"Only {fraction * 100:.0f}% of the AOI was cloud-free across the composite. "
            "Statistics are computed from that subset and may not represent the whole "
            "field."
        )

    if statistics.mean is None:
        warnings.append(
            "No cloud-free pixels remained after masking, so no NDVI statistics could "
            "be computed for this window."
        )

    if cloud_threshold >= 80:
        warnings.append(
            f"The scene cloud-cover limit is high ({cloud_threshold:.0f}%). Per-pixel "
            "masking still applies, but very cloudy scenes leave more residual haze "
            "and unmasked shadow."
        )

    if window_days > 60:
        warnings.append(
            f"The {window_days}-day window is long enough for real crop development to "
            "occur inside it. A composite over this period blends multiple growth "
            "stages; narrow the window for a snapshot of current condition."
        )

    if statistics.mean is not None and statistics.mean < 0.15:
        warnings.append(
            "Mean NDVI is very low. Before reading this as crop stress, check the "
            "true-colour layer: bare soil, a recently harvested or tilled field, water "
            "and unmasked cloud all produce low NDVI."
        )

    if statistics.max is not None and statistics.max > 0.85:
        warnings.append(
            "Part of the field exceeds NDVI 0.85, where the index saturates. "
            "Differences within that area are not reliably resolved."
        )

    return warnings


def build_class_area_note(health: HealthSummary, aoi_area_ha: float) -> str | None:
    """Note the gap between classified area and AOI area, when it is material.

    Returns None when at least 95% of the AOI was classified.
    """
    if aoi_area_ha <= 0:
        return None
    covered = health.classified_area_ha / aoi_area_ha
    if covered >= 0.95:
        return None
    return (
        f"Health classes cover {health.classified_area_ha:.2f} ha of the "
        f"{aoi_area_ha:.2f} ha AOI ({covered * 100:.0f}%). The remainder had no "
        "cloud-free observation and is excluded from the class percentages."
    )


def health_class_keys() -> list[str]:
    """All health-class keys in ascending vigour order."""
    return [definition.key for definition in HEALTH_CLASSES]
