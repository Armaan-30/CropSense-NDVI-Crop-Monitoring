"""Tests for the pure-Python analytics in :mod:`app.services.metrics`.

These cover the arithmetic that would otherwise only be exercised by a live
Earth Engine call: statistics parsing, per-class area/percentage maths, trend
fitting and warning generation.
"""

from __future__ import annotations

import pytest

from app.schemas.common import NDVIStatistics
from app.schemas.ndvi import TimeSeriesPoint
from app.services import metrics

THRESHOLDS = [0.2, 0.4, 0.6, 0.8]


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def test_epoch_ms_to_date_str() -> None:
    # 2024-01-15T10:30:00Z
    assert metrics.epoch_ms_to_date_str(1705314600000) == "2024-01-15"


def test_epoch_ms_handles_none() -> None:
    assert metrics.epoch_ms_to_iso(None) is None
    assert metrics.epoch_ms_to_date_str(None) is None


def test_epoch_ms_handles_garbage() -> None:
    assert metrics.epoch_ms_to_iso("not-a-number") is None


def test_utc_now_iso_ends_with_z() -> None:
    assert metrics.utc_now_iso().endswith("Z")


# ---------------------------------------------------------------------------
# Zonal statistics parsing
# ---------------------------------------------------------------------------
def test_parse_zonal_statistics_maps_combined_reducer_keys() -> None:
    raw = {
        "NDVI_mean": 0.6234567,
        "NDVI_min": 0.11,
        "NDVI_max": 0.89,
        "NDVI_p50": 0.64,
        "NDVI_stdDev": 0.12,
        "NDVI_p10": 0.31,
        "NDVI_p90": 0.82,
        "NDVI_count": 4321,
    }
    stats = metrics.parse_zonal_statistics(
        raw, band="NDVI", scale_m=10, valid_area_m2=80_000.0, aoi_area_m2=100_000.0
    )
    assert stats.mean == 0.6235
    assert stats.min == 0.11
    assert stats.max == 0.89
    assert stats.median == 0.64
    assert stats.std_dev == 0.12
    assert stats.p10 == 0.31
    assert stats.p90 == 0.82
    assert stats.valid_pixel_count == 4321
    assert stats.valid_pixel_fraction == 0.8
    assert stats.total_pixel_count == 1000  # 100_000 m2 / (10 m * 10 m)
    assert stats.scale_m == 10


def test_parse_zonal_statistics_fully_masked_region_returns_none() -> None:
    """A fully clouded AOI returns nulls from Earth Engine, not zeros."""
    raw = {"NDVI_mean": None, "NDVI_min": None, "NDVI_max": None, "NDVI_p50": None}
    stats = metrics.parse_zonal_statistics(
        raw, band="NDVI", scale_m=10, valid_area_m2=0.0, aoi_area_m2=100_000.0
    )
    assert stats.mean is None
    assert stats.median is None
    assert stats.valid_pixel_fraction == 0.0


def test_parse_zonal_statistics_handles_missing_payload() -> None:
    stats = metrics.parse_zonal_statistics(None, band="NDVI", scale_m=20)
    assert stats.mean is None
    assert stats.valid_pixel_fraction is None
    assert stats.scale_m == 20


def test_parse_zonal_statistics_clamps_valid_fraction() -> None:
    """Edge-pixel weighting can make valid area marginally exceed AOI area."""
    stats = metrics.parse_zonal_statistics(
        {"NDVI_mean": 0.5},
        band="NDVI",
        scale_m=10,
        valid_area_m2=101_000.0,
        aoi_area_m2=100_000.0,
    )
    assert stats.valid_pixel_fraction == 1.0


def test_parse_zonal_statistics_rejects_non_finite() -> None:
    stats = metrics.parse_zonal_statistics(
        {"NDVI_mean": float("nan"), "NDVI_min": float("inf")}, band="NDVI", scale_m=10
    )
    assert stats.mean is None
    assert stats.min is None


# ---------------------------------------------------------------------------
# Health summary
# ---------------------------------------------------------------------------
def test_build_health_summary_percentages_sum_to_100() -> None:
    grouped = {
        "groups": [
            {"class": 1, "sum": 10_000.0, "count": 100},
            {"class": 3, "sum": 30_000.0, "count": 300},
            {"class": 4, "sum": 60_000.0, "count": 600},
        ]
    }
    summary = metrics.build_health_summary(
        grouped, thresholds=THRESHOLDS, thresholds_source="server_default"
    )

    assert len(summary.classes) == 5  # absent classes still reported, as zeros
    by_key = {stat.key: stat for stat in summary.classes}
    assert by_key["very_low"].area_ha == 1.0
    assert by_key["moderate"].area_ha == 3.0
    assert by_key["healthy"].area_ha == 6.0
    assert by_key["low"].area_ha == 0.0
    assert by_key["very_healthy"].area_ha == 0.0
    assert by_key["healthy"].percent_of_valid == 60.0
    assert sum(stat.percent_of_valid for stat in summary.classes) == pytest.approx(100.0)
    assert summary.dominant_class == "healthy"
    assert summary.classified_area_ha == 10.0
    assert summary.thresholds_source == "server_default"
    assert "calibrate" in summary.calibration_note.lower()


def test_build_health_summary_class_bounds_match_thresholds() -> None:
    summary = metrics.build_health_summary(
        {"groups": []}, thresholds=THRESHOLDS, thresholds_source="request"
    )
    by_key = {stat.key: stat for stat in summary.classes}
    assert by_key["very_low"].ndvi_min is None
    assert by_key["very_low"].ndvi_max == 0.2
    assert by_key["moderate"].ndvi_min == 0.4
    assert by_key["moderate"].ndvi_max == 0.6
    assert by_key["very_healthy"].ndvi_min == 0.8
    assert by_key["very_healthy"].ndvi_max is None


def test_build_health_summary_custom_thresholds_are_echoed() -> None:
    custom = [0.1, 0.25, 0.45, 0.7]
    summary = metrics.build_health_summary(
        {"groups": []}, thresholds=custom, thresholds_source="request"
    )
    assert summary.thresholds == custom
    assert summary.thresholds_source == "request"


def test_build_health_summary_empty_result_has_no_dominant_class() -> None:
    summary = metrics.build_health_summary(
        None, thresholds=THRESHOLDS, thresholds_source="server_default"
    )
    assert summary.dominant_class is None
    assert summary.classified_area_ha == 0.0
    assert all(stat.percent_of_valid == 0.0 for stat in summary.classes)


def test_build_health_summary_skips_malformed_groups() -> None:
    grouped = {"groups": [{"class": "oops", "sum": 5.0}, {"class": 2, "sum": 20_000.0}]}
    summary = metrics.build_health_summary(
        grouped, thresholds=THRESHOLDS, thresholds_source="server_default"
    )
    assert summary.classified_area_ha == 2.0
    assert summary.dominant_class == "low"


# ---------------------------------------------------------------------------
# Trend fitting
# ---------------------------------------------------------------------------
def _point(day: str, mean: float | None) -> TimeSeriesPoint:
    return TimeSeriesPoint(date=day, mean_ndvi=mean, valid_pixel_fraction=0.9)


def test_fit_linear_trend_detects_increase() -> None:
    points = [
        _point("2024-03-01", 0.30),
        _point("2024-03-11", 0.40),
        _point("2024-03-21", 0.50),
        _point("2024-03-31", 0.60),
    ]
    trend = metrics.fit_linear_trend(points)
    assert trend.direction == "increasing"
    assert trend.n_points == 4
    assert trend.slope_ndvi_per_day == pytest.approx(0.01, abs=1e-6)
    assert trend.slope_ndvi_per_30_days == pytest.approx(0.30, abs=1e-3)
    assert trend.r_squared == pytest.approx(1.0, abs=1e-6)
    assert trend.absolute_change == pytest.approx(0.30, abs=1e-6)


def test_fit_linear_trend_detects_decrease() -> None:
    points = [
        _point("2024-05-01", 0.70),
        _point("2024-05-11", 0.58),
        _point("2024-05-21", 0.46),
        _point("2024-05-31", 0.34),
    ]
    trend = metrics.fit_linear_trend(points)
    assert trend.direction == "decreasing"
    assert trend.slope_ndvi_per_30_days is not None
    assert trend.slope_ndvi_per_30_days < 0
    # The decline wording must not assert a cause.
    assert "cannot distinguish" in trend.interpretation


def test_fit_linear_trend_reports_stable_within_noise_band() -> None:
    points = [
        _point("2024-04-01", 0.500),
        _point("2024-04-11", 0.502),
        _point("2024-04-21", 0.499),
        _point("2024-05-01", 0.501),
    ]
    trend = metrics.fit_linear_trend(points)
    assert trend.direction == "stable"


def test_fit_linear_trend_needs_minimum_points() -> None:
    trend = metrics.fit_linear_trend([_point("2024-03-01", 0.4), _point("2024-03-11", 0.5)])
    assert trend.direction == "insufficient_data"
    assert trend.slope_ndvi_per_day is None
    assert trend.absolute_change == pytest.approx(0.1, abs=1e-6)
    assert "too few" in trend.interpretation


def test_fit_linear_trend_ignores_points_without_values() -> None:
    points = [
        _point("2024-03-01", 0.30),
        _point("2024-03-11", None),
        _point("2024-03-21", 0.50),
        _point("2024-03-31", 0.60),
    ]
    trend = metrics.fit_linear_trend(points)
    assert trend.n_points == 3


def test_fit_linear_trend_handles_identical_dates() -> None:
    points = [_point("2024-03-01", 0.3), _point("2024-03-01", 0.4), _point("2024-03-01", 0.5)]
    trend = metrics.fit_linear_trend(points)
    assert trend.direction == "insufficient_data"
    assert "same date" in trend.interpretation


def test_fit_linear_trend_empty_series() -> None:
    trend = metrics.fit_linear_trend([])
    assert trend.direction == "insufficient_data"
    assert trend.n_points == 0


def test_fit_linear_trend_flags_long_window() -> None:
    points = [_point(f"2024-{month:02d}-01", 0.3 + month * 0.05) for month in range(1, 8)]
    trend = metrics.fit_linear_trend(points)
    assert "misleading" in trend.interpretation


# ---------------------------------------------------------------------------
# Area maths
# ---------------------------------------------------------------------------
def test_m2_to_ha() -> None:
    assert metrics.m2_to_ha(25_000.0) == 2.5
    assert metrics.m2_to_ha(None) == 0.0


def test_safe_percent_guards_zero_denominator() -> None:
    assert metrics.safe_percent(5.0, 0.0) == 0.0
    assert metrics.safe_percent(5.0, None) == 0.0
    assert metrics.safe_percent(25.0, 200.0) == 12.5


def test_mean_or_none() -> None:
    assert metrics.mean_or_none([1.0, 2.0, None, 3.0]) == 2.0
    assert metrics.mean_or_none([None, None]) is None
    assert metrics.mean_or_none([]) is None


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------
def test_single_scene_produces_warning() -> None:
    stats = NDVIStatistics(mean=0.5, valid_pixel_fraction=0.95)
    warnings = metrics.build_quality_warnings(
        scene_count=1, statistics=stats, cloud_threshold=20, window_days=10
    )
    assert any("one Sentinel-2 scene" in warning for warning in warnings)


def test_low_valid_fraction_produces_warning() -> None:
    stats = NDVIStatistics(mean=0.5, valid_pixel_fraction=0.12)
    warnings = metrics.build_quality_warnings(
        scene_count=5, statistics=stats, cloud_threshold=20, window_days=30
    )
    assert any("12% of the AOI was cloud-free" in warning for warning in warnings)


def test_no_valid_pixels_produces_warning() -> None:
    stats = NDVIStatistics(mean=None, valid_pixel_fraction=0.0)
    warnings = metrics.build_quality_warnings(
        scene_count=3, statistics=stats, cloud_threshold=20, window_days=30
    )
    assert any("No cloud-free pixels remained" in warning for warning in warnings)


def test_saturation_warning_above_085() -> None:
    stats = NDVIStatistics(mean=0.7, max=0.92, valid_pixel_fraction=0.9)
    warnings = metrics.build_quality_warnings(
        scene_count=6, statistics=stats, cloud_threshold=20, window_days=20
    )
    assert any("saturates" in warning for warning in warnings)


def test_low_ndvi_warning_mentions_bare_soil_before_stress() -> None:
    stats = NDVIStatistics(mean=0.09, valid_pixel_fraction=0.95)
    warnings = metrics.build_quality_warnings(
        scene_count=4, statistics=stats, cloud_threshold=20, window_days=15
    )
    assert any("bare soil" in warning for warning in warnings)


def test_clean_result_produces_no_warnings() -> None:
    stats = NDVIStatistics(mean=0.55, max=0.78, valid_pixel_fraction=0.97)
    warnings = metrics.build_quality_warnings(
        scene_count=8, statistics=stats, cloud_threshold=25, window_days=30
    )
    assert warnings == []


def test_class_area_note_only_when_coverage_is_low() -> None:
    full = metrics.build_health_summary(
        {"groups": [{"class": 4, "sum": 100_000.0, "count": 1000}]},
        thresholds=THRESHOLDS,
        thresholds_source="server_default",
    )
    assert metrics.build_class_area_note(full, aoi_area_ha=10.0) is None

    partial = metrics.build_health_summary(
        {"groups": [{"class": 4, "sum": 50_000.0, "count": 500}]},
        thresholds=THRESHOLDS,
        thresholds_source="server_default",
    )
    note = metrics.build_class_area_note(partial, aoi_area_ha=10.0)
    assert note is not None
    assert "50%" in note


def test_health_class_keys_ordered_by_vigour() -> None:
    assert metrics.health_class_keys() == [
        "very_low",
        "low",
        "moderate",
        "healthy",
        "very_healthy",
    ]
