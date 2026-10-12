"""Aggregate API router.

``system`` routes declare their own absolute paths (``/health`` must not be
prefixed), so they are mounted at the root. Analysis routers are mounted under
the configurable API prefix.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import history, ndvi, system
from app.core.config import get_settings

settings = get_settings()

api_router = APIRouter()

# /health and /api/system/* declare full paths internally.
api_router.include_router(system.router)

# /api/ndvi/*
api_router.include_router(ndvi.router, prefix=settings.api_prefix)
api_router.include_router(history.router, prefix=settings.api_prefix)
