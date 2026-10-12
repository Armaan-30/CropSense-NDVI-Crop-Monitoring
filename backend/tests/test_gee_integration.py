"""Small, opt-in live Earth Engine smoke test for the public analyze route."""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("CROPSENSE_RUN_INTEGRATION") != "1",
    reason="Set CROPSENSE_RUN_INTEGRATION=1 and configure Earth Engine credentials to run.",
)
def test_live_analyze_returns_real_sentinel2_result() -> None:
    """Exercise a ~1 ha AOI over a 30-day window with modest pixel demand."""
    from app.main import app

    end_date = date.today() - timedelta(days=5)  # allow recent scenes to ingest
    start_date = end_date - timedelta(days=29)
    half_lon = 0.0005  # roughly 48 m at this latitude
    half_lat = 0.00045  # roughly 50 m
    # Small sample AOI near Jalgaon, Maharashtra. This only confirms that the
    # public analysis route can query real imagery in the user's target state;
    # it is not a supplied or verified farm boundary.
    center_lon, center_lat = 75.55, 21.00
    aoi = {
        "type": "Polygon",
        "coordinates": [
            [
                [center_lon - half_lon, center_lat - half_lat],
                [center_lon + half_lon, center_lat - half_lat],
                [center_lon + half_lon, center_lat + half_lat],
                [center_lon - half_lon, center_lat + half_lat],
                [center_lon - half_lon, center_lat - half_lat],
            ]
        ],
    }
    payload = {
        "aoi": aoi,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "cloud_threshold": 100,
        "options": {
            "cloud_mask_method": "scl",
            "composite_method": "median",
            "scale_m": 20,
            "include_true_color_layer": False,
        },
    }

    # No `client` fixture: it deliberately overrides the Earth Engine service
    # with a stub. The integration-mode autouse fixture leaves the real service
    # active, so TestClient exercises the same route and lifespan as the app.
    with TestClient(app) as client:
        response = client.post("/api/ndvi/analyze", json=payload)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["imagery"]["collection_id"] == "COPERNICUS/S2_SR_HARMONIZED"
    assert result["imagery"]["scene_count"] > 0
    assert result["imagery"]["scene_ids"]
    assert result["statistics"]["scale_m"] == 20
    assert len(result["health"]["classes"]) == 5
    assert {layer["id"] for layer in result["layers"]} >= {"ndvi", "health"}
    assert all(layer["tile_url_template"] for layer in result["layers"])
