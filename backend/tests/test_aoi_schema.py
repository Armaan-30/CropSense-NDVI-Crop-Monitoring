"""Tests for AOI GeoJSON validation and normalisation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.aoi import GeoJSONGeometry, normalize_geojson

SQUARE = [
    [
        [75.80, 30.90],
        [75.81, 30.90],
        [75.81, 30.91],
        [75.80, 30.91],
        [75.80, 30.90],
    ]
]


def test_polygon_accepted() -> None:
    geometry = GeoJSONGeometry(type="Polygon", coordinates=SQUARE)
    assert geometry.to_dict() == {"type": "Polygon", "coordinates": SQUARE}


def test_point_accepted() -> None:
    geometry = GeoJSONGeometry(type="Point", coordinates=[75.8, 30.9])
    assert geometry.type == "Point"


def test_multipolygon_accepted() -> None:
    geometry = GeoJSONGeometry(type="MultiPolygon", coordinates=[SQUARE])
    assert geometry.type == "MultiPolygon"


def test_polygon_ring_needs_four_positions() -> None:
    short_ring = [[[75.80, 30.90], [75.81, 30.90], [75.80, 30.90]]]
    with pytest.raises(ValidationError, match="at least 4 positions"):
        GeoJSONGeometry(type="Polygon", coordinates=short_ring)


def test_longitude_out_of_range_rejected() -> None:
    bad = [[[275.0, 30.90], [75.81, 30.90], [75.81, 30.91], [275.0, 30.90]]]
    with pytest.raises(ValidationError, match="longitude"):
        GeoJSONGeometry(type="Polygon", coordinates=bad)


def test_latitude_out_of_range_rejected() -> None:
    bad = [[[75.80, 130.0], [75.81, 30.90], [75.81, 30.91], [75.80, 130.0]]]
    with pytest.raises(ValidationError, match="latitude"):
        GeoJSONGeometry(type="Polygon", coordinates=bad)


def test_empty_coordinates_rejected() -> None:
    with pytest.raises(ValidationError):
        GeoJSONGeometry(type="Polygon", coordinates=[])


def test_unsupported_geometry_type_rejected() -> None:
    with pytest.raises(ValidationError):
        GeoJSONGeometry(type="LineString", coordinates=[[0, 0], [1, 1]])


# --- normalize_geojson -----------------------------------------------------


def test_normalize_passes_through_geometry() -> None:
    payload = {"type": "Polygon", "coordinates": SQUARE}
    assert normalize_geojson(payload) == payload


def test_normalize_unwraps_feature() -> None:
    payload = {
        "type": "Feature",
        "properties": {"name": "field-1"},
        "geometry": {"type": "Polygon", "coordinates": SQUARE},
    }
    assert normalize_geojson(payload) == {"type": "Polygon", "coordinates": SQUARE}


def test_normalize_unwraps_single_feature_collection() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": SQUARE}}],
    }
    assert normalize_geojson(payload) == {"type": "Polygon", "coordinates": SQUARE}


def test_normalize_rejects_multi_feature_collection() -> None:
    feature = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": SQUARE}}
    payload = {"type": "FeatureCollection", "features": [feature, feature]}
    with pytest.raises(ValueError, match="exactly one feature"):
        normalize_geojson(payload)


def test_normalize_rejects_feature_without_geometry() -> None:
    with pytest.raises(ValueError, match="missing a geometry"):
        normalize_geojson({"type": "Feature", "properties": {}})


def test_normalize_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="Unsupported AOI geometry type"):
        normalize_geojson({"type": "GeometryCollection", "geometries": []})


def test_normalize_rejects_non_dict() -> None:
    with pytest.raises(ValueError, match="GeoJSON object"):
        normalize_geojson("not a dict")  # type: ignore[arg-type]
