"""CropSense FastAPI application.

Satellite-based crop health monitoring using Sentinel-2 NDVI, served through
Google Earth Engine.

Run locally::

    uvicorn app.main:app --reload --port 8000

Interactive docs: http://localhost:8000/docs
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import api_router
from app.core.config import get_settings
from app.core.exceptions import CropSenseError
from app.core.logging_config import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)

DESCRIPTION = """
CropSense analyses agricultural vegetation condition from Sentinel-2 Level-2A
surface reflectance using Google Earth Engine.

**What it does**

* Filters Sentinel-2 imagery by area of interest, date range and cloud cover.
* Masks cloud, cirrus and cloud shadow per pixel (Cloud Score+ by default).
* Computes `NDVI = (B8 - B4) / (B8 + B4)` at 10 m.
* Reports mean / min / max / median NDVI and percentile spread over the AOI.
* Classifies vegetation condition into five configurable categories.
* Tracks NDVI over time and fits a linear trend.
* Screens for areas of significant NDVI decline between two periods.
* Returns signed Earth Engine tile URLs for map display, with no credential
  exposure to the browser.

**What it does not do**

NDVI measures vegetation vigour. It does not diagnose crop disease, identify
pests, or determine the cause of any change. Flagged areas indicate *potential*
stress that requires ground verification. No accuracy or validation metrics are
reported, because none have been established for this deployment.

**Threshold calibration**

The NDVI health-class boundaries are configurable and their defaults are generic
starting points. Absolute NDVI values indicating a healthy crop vary with crop
type, growth stage, canopy structure, soil background, region and season.
Calibrate them against ground observations before operational use.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Attempt Earth Engine initialisation at start-up.

    By default a failure is logged but not fatal, so the service still boots and
    ``/health`` can explain what is missing. Set ``EE_FAIL_FAST=true`` to abort
    start-up instead - appropriate in production where a misconfigured instance
    should never accept traffic.
    """
    logger.info("Starting %s v%s (env=%s)", settings.app_name, __version__, settings.app_env)

    # Imported here so the module-level import graph stays light and tests can
    # patch the service before start-up.
    from app.services.gee_service import get_gee_service

    try:
        get_gee_service().initialize()
    except Exception as exc:
        if settings.ee_fail_fast:
            logger.critical("Earth Engine initialisation failed and EE_FAIL_FAST is set: %s", exc)
            raise
        logger.warning(
            "Earth Engine is not available yet: %s. The API is running in degraded "
            "mode - GET /health reports what needs configuring.",
            exc,
        )

    yield

    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(CropSenseError)
async def cropsense_error_handler(request: Request, exc: CropSenseError) -> JSONResponse:
    """Render domain errors through the uniform error envelope.

    Client-caused failures (4xx) log at WARNING; server/upstream failures (5xx)
    log at ERROR, so alerting can key off log level.
    """
    log = logger.warning if exc.status_code < 500 else logger.error
    log("%s %s -> %s: %s", request.method, request.url.path, exc.code, exc.message)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return Pydantic validation failures in the same envelope as domain errors."""
    logger.warning("Validation error on %s: %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "The request body failed validation. See details.",
            # jsonable-safe: FastAPI's errors() can contain non-serialisable ctx values.
            "details": {"errors": _serialisable_errors(exc)},
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all so an unexpected failure never leaks a stack trace to a client."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "code": "internal_error",
            "message": "An unexpected server error occurred. Check the server logs.",
            "details": {},
        },
    )


def _serialisable_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    """Strip non-JSON-serialisable values out of validation error details."""
    cleaned: list[dict[str, object]] = []
    for error in exc.errors():
        cleaned.append(
            {
                "location": [str(part) for part in error.get("loc", ())],
                "message": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
        )
    return cleaned


app.include_router(api_router)


@app.get("/", tags=["system"], summary="API index")
def root() -> dict[str, object]:
    """Minimal service index with links to docs and the key endpoints."""
    return {
        "name": settings.app_name,
        "version": __version__,
        "description": "Satellite-based crop health monitoring using Sentinel-2 NDVI.",
        "docs": "/docs",
        "endpoints": {
            "health": "/health",
            "config": "/api/system/config",
            "earth_engine_test": "/api/system/gee-test",
            "analyze": f"{settings.api_prefix}/ndvi/analyze",
            "timeseries": f"{settings.api_prefix}/ndvi/timeseries",
            "change": f"{settings.api_prefix}/ndvi/change",
        },
    }
