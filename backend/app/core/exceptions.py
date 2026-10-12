"""Domain exceptions for CropSense.

Each exception carries an HTTP status code and a stable machine-readable
``code`` so the frontend can branch on failure type (e.g. show "no cloud-free
imagery in this window, try widening the date range" rather than a generic
500).
"""

from __future__ import annotations

from typing import Any


class CropSenseError(Exception):
    """Base class for all CropSense application errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the API error envelope."""
        return {"code": self.code, "message": self.message, "details": self.details}


class ConfigurationError(CropSenseError):
    """Required configuration is missing or invalid."""

    status_code = 500
    code = "configuration_error"


class EarthEngineAuthError(CropSenseError):
    """Earth Engine credentials are missing, invalid, or lack permissions.

    This is deliberately distinct from a transient Earth Engine failure: it
    tells the operator to fix credentials rather than retry.
    """

    status_code = 503
    code = "earth_engine_auth_error"


class EarthEngineError(CropSenseError):
    """Earth Engine rejected a request or failed while computing it."""

    status_code = 502
    code = "earth_engine_error"


class NoImageryError(CropSenseError):
    """No Sentinel-2 scenes match the AOI / date range / cloud filter.

    A legitimate, expected outcome - not a bug. Cloud-heavy monsoon windows
    and short date ranges over small AOIs routinely produce zero usable
    scenes.
    """

    status_code = 404
    code = "no_imagery"


class InvalidAOIError(CropSenseError):
    """The supplied Area of Interest geometry is invalid or out of bounds."""

    status_code = 422
    code = "invalid_aoi"


class InvalidRequestError(CropSenseError):
    """The request is well-formed JSON but semantically invalid."""

    status_code = 422
    code = "invalid_request"
