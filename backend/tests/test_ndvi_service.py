"""Tests for the parts of :class:`NDVIService` that need no Earth Engine call.

Threshold resolution, visualisation parameters and legends are pure functions of
configuration, so they are worth pinning down without credentials. The Earth
Engine expression builders (``add_ndvi_band``, ``classify_health``, ...) require
an initialised client and are covered by the integration tests instead.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.models.vegetation import (
    CHANGE_DISPLAY_MAX,
    CHANGE_DISPLAY_MIN,
    CHANGE_PALETTE,
    HEALTH_CLASSES,
    HEALTH_PALETTE,
    NDVI_DISPLAY_MAX,
    NDVI_DISPLAY_MIN,
    NDVI_PALETTE,
    STRESS_COLOR,
)
from app.services.ndvi_service import (
    CHANGE_BAND,
    DECLINE_BAND,
    HEALTH_BAND,
    NDVI_BAND,
    NDVIService,
)


@pytest.fixture
def service() -> NDVIService:
    """An NDVI service with a stub Earth Engine client (never called here)."""
    from tests.conftest import StubGEEService

    return NDVIService(StubGEEService(), Settings(ndvi_class_thresholds="0.2,0.4,0.6,0.8"))


# ---------------------------------------------------------------------------
# Threshold resolution
# ---------------------------------------------------------------------------
def test_resolve_thresholds_falls_back_to_server_default(service: NDVIService) -> None:
    thresholds, source = service.resolve_thresholds(None)
    assert thresholds == [0.2, 0.4, 0.6, 0.8]
    assert source == "server_default"


def test_resolve_thresholds_prefers_request_override(service: NDVIService) -> None:
    thresholds, source = service.resolve_thresholds([0.1, 0.25, 0.45, 0.70])
    assert thresholds == [0.1, 0.25, 0.45, 0.70]
    assert source == "request"


def test_resolve_thresholds_rejects_bad_override(service: NDVIService) -> None:
    with pytest.raises(ValueError):
        service.resolve_thresholds([0.5, 0.2, 0.6, 0.8])


def test_configured_thresholds_are_honoured() -> None:
    from tests.conftest import StubGEEService

    custom = NDVIService(StubGEEService(), Settings(ndvi_class_thresholds="0.05,0.15,0.30,0.55"))
    thresholds, source = custom.resolve_thresholds(None)
    assert thresholds == [0.05, 0.15, 0.30, 0.55]
    assert source == "server_default"


# ---------------------------------------------------------------------------
# Visualisation parameters
# ---------------------------------------------------------------------------
def test_ndvi_vis_params(service: NDVIService) -> None:
    params = service.ndvi_vis_params()
    assert params["bands"] == [NDVI_BAND]
    assert params["min"] == NDVI_DISPLAY_MIN
    assert params["max"] == NDVI_DISPLAY_MAX
    assert params["palette"] == list(NDVI_PALETTE)


def test_health_vis_params_span_all_class_codes(service: NDVIService) -> None:
    params = service.health_vis_params()
    assert params["bands"] == [HEALTH_BAND]
    assert params["min"] == HEALTH_CLASSES[0].code
    assert params["max"] == HEALTH_CLASSES[-1].code
    # One palette entry per discrete class, or Earth Engine would interpolate.
    assert len(params["palette"]) == len(HEALTH_CLASSES)
    assert params["palette"] == list(HEALTH_PALETTE)


def test_change_vis_params_are_symmetric(service: NDVIService) -> None:
    params = service.change_vis_params()
    assert params["bands"] == [CHANGE_BAND]
    assert params["min"] == CHANGE_DISPLAY_MIN
    assert params["max"] == CHANGE_DISPLAY_MAX
    assert params["min"] == -params["max"]
    assert params["palette"] == list(CHANGE_PALETTE)
    # A diverging palette needs an odd bin count so zero sits on the neutral hue.
    assert len(CHANGE_PALETTE) % 2 == 1


def test_decline_vis_params_single_colour(service: NDVIService) -> None:
    params = service.decline_vis_params()
    assert params["bands"] == [DECLINE_BAND]
    assert params["palette"] == [STRESS_COLOR]


def test_true_color_vis_params_use_configured_red_band(service: NDVIService) -> None:
    params = service.true_color_vis_params()
    assert params["bands"] == ["B4", "B3", "B2"]
    assert params["min"] < params["max"] <= 1.0


def test_true_color_vis_params_follow_band_config() -> None:
    from tests.conftest import StubGEEService

    custom = NDVIService(StubGEEService(), Settings(band_red="B04"))
    assert custom.true_color_vis_params()["bands"][0] == "B04"


# ---------------------------------------------------------------------------
# Legends
# ---------------------------------------------------------------------------
def test_ndvi_legend_covers_display_range_without_gaps(service: NDVIService) -> None:
    stops = service.ndvi_legend()
    assert len(stops) == len(NDVI_PALETTE)
    assert stops[0].value_min == pytest.approx(NDVI_DISPLAY_MIN)
    assert stops[-1].value_max == pytest.approx(NDVI_DISPLAY_MAX)
    for index in range(len(stops) - 1):
        assert stops[index].value_max == pytest.approx(stops[index + 1].value_min)


def test_health_legend_labels_show_real_bounds(service: NDVIService) -> None:
    stops = service.health_legend([0.2, 0.4, 0.6, 0.8])
    assert len(stops) == len(HEALTH_CLASSES)
    assert "< 0.20" in stops[0].label
    assert ">= 0.80" in stops[-1].label
    assert "0.40" in stops[2].label and "0.60" in stops[2].label


def test_health_legend_reflects_custom_thresholds(service: NDVIService) -> None:
    stops = service.health_legend([0.05, 0.15, 0.30, 0.55])
    assert "< 0.05" in stops[0].label
    assert ">= 0.55" in stops[-1].label


def test_health_legend_colors_match_class_definitions(service: NDVIService) -> None:
    stops = service.health_legend([0.2, 0.4, 0.6, 0.8])
    assert [stop.color for stop in stops] == [d.color for d in HEALTH_CLASSES]


def test_change_legend_is_centred_on_zero(service: NDVIService) -> None:
    stops = service.change_legend()
    assert stops[0].value_min == pytest.approx(CHANGE_DISPLAY_MIN)
    assert stops[-1].value_max == pytest.approx(CHANGE_DISPLAY_MAX)
    midpoint = stops[len(stops) // 2]
    assert midpoint.value_min < 0 < midpoint.value_max
