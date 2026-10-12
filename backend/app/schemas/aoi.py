"""Area-of-Interest (AOI) schemas and GeoJSON normalisation.

The frontend draws a field on a Leaflet map and sends the resulting GeoJSON.
We accept the shapes a mapping client realistically produces - a bare
geometry, a ``Feature``, or a single-member ``FeatureCollection`` - and
normalise them all down to one geometry dict that the Earth Engine layer can
consume.

Coordinates are expected in EPSG:4326 (WGS 84 longitude/latitude), which is
what GeoJSON mandates and what Leaflet emits.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

GeometryType = Literal["Point", "Polygon", "MultiPolygon"]

SUPPORTED_GEOMETRY_TYPES: tuple[str, ...] = ("Point", "Polygon", "MultiPolygon")


class GeoJSONGeometry(BaseModel):
    """A GeoJSON geometry restricted to the types CropSense supports.

    ``Point`` is accepted so a user can click a location and have it buffered
    into a circular AOI (see :attr:`AOIRequest.buffer_m`).
    """

    model_config = ConfigDict(extra="ignore")

    type: GeometryType
    coordinates: Any = Field(
        ...,
        description="GeoJSON coordinate array. Nesting depth depends on `type`.",
    )

    @field_validator("coordinates")
    @classmethod
    def _validate_coordinates_present(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("coordinates must not be null")
        if isinstance(value, (list, tuple)) and len(value) == 0:
            raise ValueError("coordinates must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> GeoJSONGeometry:
        """Structurally validate the coordinate nesting for the declared type."""
        coords = self.coordinates

        if self.type == "Point":
            _require_position(coords, "Point coordinates")
        elif self.type == "Polygon":
            _require_polygon(coords, "Polygon coordinates")
        elif self.type == "MultiPolygon":
            if not isinstance(coords, (list, tuple)) or not coords:
                raise ValueError("MultiPolygon coordinates must be a non-empty array")
            for index, polygon in enumerate(coords):
                _require_polygon(polygon, f"MultiPolygon polygon[{index}]")

        return self

    def to_dict(self) -> dict[str, Any]:
        """Return a plain GeoJSON geometry dict."""
        return {"type": self.type, "coordinates": self.coordinates}


def _require_position(value: Any, label: str) -> None:
    """Validate a single [lon, lat] position."""
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise ValueError(f"{label} must be [longitude, latitude]")
    lon, lat = value[0], value[1]
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        raise ValueError(f"{label} must be numeric")
    if not -180.0 <= float(lon) <= 180.0:
        raise ValueError(f"{label}: longitude {lon} outside [-180, 180]")
    if not -90.0 <= float(lat) <= 90.0:
        raise ValueError(f"{label}: latitude {lat} outside [-90, 90]")


def _require_polygon(value: Any, label: str) -> None:
    """Validate a polygon coordinate array (list of linear rings)."""
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{label} must be a non-empty array of linear rings")
    for ring_index, ring in enumerate(value):
        if not isinstance(ring, (list, tuple)):
            raise ValueError(f"{label} ring[{ring_index}] must be an array of positions")
        if len(ring) < 4:
            raise ValueError(
                f"{label} ring[{ring_index}] needs at least 4 positions "
                "(a closed ring); got "
                f"{len(ring)}"
            )
        for position in ring:
            _require_position(position, f"{label} ring[{ring_index}]")


def normalize_geojson(payload: dict[str, Any]) -> dict[str, Any]:
    """Reduce any accepted GeoJSON envelope to a single geometry dict.

    Accepts a geometry, a ``Feature``, or a ``FeatureCollection`` containing
    exactly one feature.

    Args:
        payload: Raw GeoJSON-ish dict from the client.

    Returns:
        A geometry dict with ``type`` and ``coordinates``.

    Raises:
        ValueError: If the payload is not a supported GeoJSON shape.
    """
    if not isinstance(payload, dict):
        raise ValueError("AOI must be a GeoJSON object")

    geo_type = payload.get("type")

    if geo_type == "FeatureCollection":
        features = payload.get("features") or []
        if len(features) != 1:
            raise ValueError(
                "AOI FeatureCollection must contain exactly one feature "
                f"(got {len(features)}). Draw or upload a single field."
            )
        return normalize_geojson(features[0])

    if geo_type == "Feature":
        geometry = payload.get("geometry")
        if not isinstance(geometry, dict):
            raise ValueError("AOI Feature is missing a geometry")
        return normalize_geojson(geometry)

    if geo_type in SUPPORTED_GEOMETRY_TYPES:
        return {"type": geo_type, "coordinates": payload.get("coordinates")}

    raise ValueError(
        f"Unsupported AOI geometry type {geo_type!r}. "
        f"Supported types: {', '.join(SUPPORTED_GEOMETRY_TYPES)}, Feature, FeatureCollection."
    )


class AOISummary(BaseModel):
    """Server-computed description of the resolved AOI."""

    geometry_type: str = Field(..., description="Resolved geometry type after normalisation.")
    area_ha: float = Field(..., description="AOI area in hectares (EPSG:4326 geodesic).")
    area_km2: float = Field(..., description="AOI area in square kilometres.")
    centroid: list[float] = Field(..., description="[longitude, latitude] of the AOI centroid.")
    bbox: list[float] = Field(
        ...,
        description="Bounding box as [min_lon, min_lat, max_lon, max_lat].",
    )
