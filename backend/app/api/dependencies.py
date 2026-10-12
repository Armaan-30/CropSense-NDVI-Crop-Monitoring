"""FastAPI dependency providers.

Routes depend on the callables here rather than reaching into the service layer
directly. That keeps the service modules framework-agnostic and gives tests a
single override point: replacing :func:`earth_engine_service` also replaces the
Earth Engine client used by :func:`analysis_service`.
"""

from __future__ import annotations

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.analysis_service import AnalysisService
from app.services.gee_service import GEEService, get_gee_service
from app.services.history_store import AnalysisHistoryStore


def app_settings() -> Settings:
    """The cached application settings."""
    return get_settings()


def earth_engine_service() -> GEEService:
    """The process-wide Earth Engine service.

    Shared rather than per-request because Earth Engine's client state is
    global to the process and initialisation is expensive.
    """
    return get_gee_service()


def analysis_service(
    gee: GEEService = Depends(earth_engine_service),
    settings: Settings = Depends(app_settings),
) -> AnalysisService:
    """A request-scoped analysis service.

    Cheap to construct - it only holds references to the shared Earth Engine
    service and the settings object.
    """
    return AnalysisService(gee=gee, settings=settings)


def analysis_history_store(
    settings: Settings = Depends(app_settings),
) -> AnalysisHistoryStore:
    """Provide local persistent analysis history."""
    return AnalysisHistoryStore(settings.resolved_database_path)
