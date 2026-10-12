"""Google Earth Engine integration service.

This is the **only** module in CropSense that talks to Earth Engine's client
lifecycle. It owns:

* authentication (service account, or local ``earthengine authenticate``
  credentials) and lazy, thread-safe initialisation;
* connectivity diagnostics used by ``/health`` and ``/api/system/gee-test``;
* geometry construction and AOI measurement;
* Sentinel-2 collection filtering (AOI, date, scene cloud cover);
* per-pixel cloud/shadow masking and reflectance scaling;
* compositing;
* region reduction (zonal statistics, class areas);
* signed XYZ tile URL generation via ``getMapId``;
* translation of ``ee.EEException`` into CropSense domain exceptions.

Nothing above this module should import ``ee`` for client concerns, and nothing
here knows what NDVI is - that lives in :mod:`app.services.ndvi_service`.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Final

import ee

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ConfigurationError,
    EarthEngineAuthError,
    EarthEngineError,
    InvalidAOIError,
    NoImageryError,
)
from app.core.logging_config import get_logger
from app.schemas.aoi import AOISummary
from app.schemas.common import CloudMaskMethod, CompositeMethod, DateRange

logger = get_logger(__name__)

# Sentinel-2 scene-level cloud metadata property.
CLOUD_PROPERTY: Final[str] = "CLOUDY_PIXEL_PERCENTAGE"

# Sen2Cor Scene Classification Layer values that we treat as unusable.
#   0 no data              1 saturated/defective   2 dark area / cast shadow
#   3 cloud shadow         8 cloud medium prob.    9 cloud high prob.
#  10 thin cirrus         11 snow / ice
# Retained: 4 vegetation, 5 not-vegetated, 6 water, 7 unclassified.
SCL_MASK_VALUES: Final[tuple[int, ...]] = (0, 1, 2, 3, 8, 9, 10, 11)

# QA60 bitmask positions.
QA60_OPAQUE_CLOUD_BIT: Final[int] = 10
QA60_CIRRUS_CLOUD_BIT: Final[int] = 11

# Cloud Score+ coverage begins with Sentinel-2 harmonised data from 2017-06-27.
CLOUD_SCORE_PLUS_START: Final[date] = date(2017, 6, 27)

# Sentinel-2A launch; nothing exists before this.
SENTINEL2_START: Final[date] = date(2015, 6, 23)

# Geometry operations tolerate this much error, in metres.
GEOMETRY_MAX_ERROR_M: Final[float] = 1.0

ATTRIBUTION: Final[str] = (
    "Contains modified Copernicus Sentinel data, processed via Google Earth Engine."
)

# Where google-auth looks for Application Default Credentials, per platform.
_ADC_RELATIVE_PATH: Final[str] = "gcloud/application_default_credentials.json"


def _local_credential_paths() -> list[Path]:
    """Candidate on-disk credential files, in the order Earth Engine consults them.

    ``ee.Initialize`` falls back to Application Default Credentials when no
    Earth Engine credentials file exists, and that fallback probes the GCE
    metadata server - roughly ten seconds of dead time on a machine that has no
    credentials at all. Checking the paths ourselves turns that into an
    instant, clearly worded failure. See
    :meth:`GEEService.local_credentials_available`.
    """
    candidates: list[Path] = []

    try:
        candidates.append(Path(ee.oauth.get_credentials_path()))
    except (AttributeError, OSError, RuntimeError):  # pragma: no cover - defensive
        candidates.append(Path.home() / ".config" / "earthengine" / "credentials")

    explicit = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if explicit:
        candidates.append(Path(explicit))

    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / _ADC_RELATIVE_PATH)
    candidates.append(Path.home() / ".config" / _ADC_RELATIVE_PATH)

    return candidates


class GEEService:
    """Stateful wrapper around the Earth Engine Python API.

    A single instance is shared process-wide (see :func:`get_gee_service`).
    Initialisation is lazy and guarded by a lock so concurrent requests cannot
    race on Earth Engine's global module state.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._lock = threading.Lock()
        self._initialized = False
        self._auth_method: str | None = None
        self._init_error: str | None = None

    # ------------------------------------------------------------------
    # Authentication and lifecycle
    # ------------------------------------------------------------------
    @property
    def initialized(self) -> bool:
        """True once ``ee.Initialize`` has succeeded in this process."""
        return self._initialized

    @property
    def auth_method(self) -> str | None:
        """``'service_account'``, ``'local_credentials'``, or None."""
        return self._auth_method

    @property
    def init_error(self) -> str | None:
        """The last initialisation failure message, if any."""
        return self._init_error

    def initialize(self, *, force: bool = False) -> None:
        """Initialise the Earth Engine client, at most once.

        Credential resolution order:

        1. Service account key (``EE_SERVICE_ACCOUNT_KEY_FILE`` or
           ``EE_SERVICE_ACCOUNT_KEY_JSON``) - preferred for servers.
        2. Local persistent credentials written by ``earthengine authenticate``
           - convenient for development, only if ``EE_USE_LOCAL_CREDENTIALS``.

        Args:
            force: Re-initialise even if already initialised.

        Raises:
            ConfigurationError: ``EE_PROJECT`` is not set.
            EarthEngineAuthError: Credentials are missing, invalid, or the
                project is not registered for Earth Engine.
        """
        if self._initialized and not force:
            return

        with self._lock:
            if self._initialized and not force:
                return

            settings = self._settings

            if not settings.ee_project:
                self._init_error = (
                    "EE_PROJECT is not set. The Earth Engine v1 API requires a "
                    "Google Cloud project that is registered for Earth Engine."
                )
                raise ConfigurationError(
                    self._init_error,
                    details={"remediation": self.remediation_steps()},
                )

            url = ee.data.HIGH_VOLUME_API_BASE_URL if settings.ee_use_high_volume_endpoint else None

            try:
                if settings.has_service_account_credentials:
                    credentials = self._build_service_account_credentials()
                    ee.Initialize(
                        credentials=credentials,
                        project=settings.ee_project,
                        url=url,
                    )
                    self._auth_method = "service_account"
                elif settings.ee_use_local_credentials:
                    self._require_local_credentials()
                    # 'persistent' reads ~/.config/earthengine/credentials.
                    ee.Initialize(project=settings.ee_project, url=url)
                    self._auth_method = "local_credentials"
                else:
                    self._init_error = (
                        "No Earth Engine credentials configured and "
                        "EE_USE_LOCAL_CREDENTIALS is disabled."
                    )
                    raise EarthEngineAuthError(
                        self._init_error,
                        details={"remediation": self.remediation_steps()},
                    )
            except Exception as exc:
                # Deliberately broad: depending on which credential path fails,
                # ee.Initialize raises ee.EEException, a google.auth error, or a
                # plain OSError. They all mean the same thing to a caller -
                # Earth Engine is unusable - so they are normalised here.
                if isinstance(exc, (EarthEngineAuthError, ConfigurationError)):
                    raise
                self._init_error = str(exc)
                logger.error(
                    "Earth Engine initialisation failed (project=%s, method=%s): %s",
                    settings.ee_project,
                    self._auth_method or "unresolved",
                    exc,
                )
                self._auth_method = None
                raise EarthEngineAuthError(
                    f"Earth Engine initialisation failed: {exc}",
                    details={"remediation": self.remediation_steps()},
                ) from exc

            self._initialized = True
            self._init_error = None
            logger.info(
                "Earth Engine initialised (project=%s, auth=%s, high_volume=%s)",
                settings.ee_project,
                self._auth_method,
                settings.ee_use_high_volume_endpoint,
            )

    def local_credentials_available(self) -> Path | None:
        """Return the first existing local credential file, or None.

        Purely a filesystem check - no network, no Earth Engine call.
        """
        for candidate in _local_credential_paths():
            try:
                if candidate.is_file():
                    return candidate
            except OSError:  # pragma: no cover - unreadable path
                continue
        return None

    def _require_local_credentials(self) -> None:
        """Fail fast when no local credential file exists.

        Skipped when ``EE_ALLOW_ADC_DISCOVERY`` is set, which is required on
        Google Cloud runtimes where credentials come from the metadata server
        rather than a file.

        Raises:
            EarthEngineAuthError: No credential file was found on disk.
        """
        if self._settings.ee_allow_adc_discovery:
            return

        found = self.local_credentials_available()
        if found is not None:
            logger.debug("Using local Earth Engine credentials at %s", found)
            return

        self._init_error = (
            "No Earth Engine credentials found. Run `earthengine authenticate` to "
            "create ~/.config/earthengine/credentials, or configure a service "
            "account via EE_SERVICE_ACCOUNT_EMAIL and EE_SERVICE_ACCOUNT_KEY_FILE."
        )
        raise EarthEngineAuthError(
            self._init_error,
            details={"remediation": self.remediation_steps()},
        )

    def _build_service_account_credentials(self) -> Any:
        """Build google-auth credentials from the configured service-account key."""
        settings = self._settings

        if settings.ee_service_account_key_json:
            key_dict = settings.service_account_key_dict or {}
            email = settings.ee_service_account_email or str(key_dict.get("client_email") or "")
            logger.info("Using inline service-account key for %s", email or "<unknown>")
            return ee.ServiceAccountCredentials(
                email=email or None,
                key_data=settings.ee_service_account_key_json,
            )

        key_file = settings.ee_service_account_key_file
        logger.info("Using service-account key file at %s", key_file)
        return ee.ServiceAccountCredentials(
            email=settings.ee_service_account_email or None,
            key_file=key_file,
        )

    def ensure_initialized(self) -> None:
        """Initialise if needed, re-raising the original failure on each call."""
        if self._initialized:
            return
        self.initialize()

    def remediation_steps(self) -> list[str]:
        """Concrete operator steps to get Earth Engine working.

        Returned verbatim in ``/health`` and ``/api/system/gee-test`` so the
        failure is actionable without reading the logs.
        """
        settings = self._settings
        steps: list[str] = []

        if not settings.ee_project:
            steps.append(
                "Set EE_PROJECT in your .env to a Google Cloud project ID that is "
                "registered for Earth Engine (register at "
                "https://code.earthengine.google.com/register)."
            )

        if not settings.has_service_account_credentials:
            steps.extend(
                [
                    "Local development: install the Earth Engine CLI "
                    "(`pip install earthengine-api`) and run `earthengine authenticate`, "
                    "then keep EE_USE_LOCAL_CREDENTIALS=true.",
                    "Server / production: create a GCP service account, grant it the "
                    "'Earth Engine Resource Viewer' role, register the service account "
                    "at https://code.earthengine.google.com/register, download a JSON "
                    "key, and set EE_SERVICE_ACCOUNT_EMAIL and "
                    "EE_SERVICE_ACCOUNT_KEY_FILE (or EE_SERVICE_ACCOUNT_KEY_JSON).",
                ]
            )
        else:
            steps.append(
                "Verify the service account is registered for Earth Engine use and has "
                "access to the EE_PROJECT, and that the key file path is readable by "
                "the API process."
            )

        steps.append(
            "Confirm the Earth Engine API is enabled on the project: "
            "https://console.cloud.google.com/apis/library/earthengine.googleapis.com"
        )
        return steps

    def status(self) -> dict[str, Any]:
        """Non-throwing snapshot of the Earth Engine connection state."""
        settings = self._settings
        try:
            self.ensure_initialized()
        except (EarthEngineAuthError, ConfigurationError) as exc:
            return {
                "initialized": False,
                "auth_method": None,
                "project": settings.ee_project,
                "service_account_email": settings.ee_service_account_email,
                "high_volume_endpoint": settings.ee_use_high_volume_endpoint,
                "error": exc.message,
                "remediation": self.remediation_steps(),
            }

        return {
            "initialized": True,
            "auth_method": self._auth_method,
            "project": settings.ee_project,
            "service_account_email": settings.ee_service_account_email,
            "high_volume_endpoint": settings.ee_use_high_volume_endpoint,
            "error": None,
            "remediation": [],
        }

    def connectivity_test(self) -> dict[str, Any]:
        """Run a small but real computation against Earth Engine servers.

        Two round trips: a trivial arithmetic evaluation (proves auth and
        network), then a tightly bounded Sentinel-2 query (proves catalogue
        access).

        Returns:
            A dict matching :class:`app.schemas.system.GEETestResponse`.
        """
        settings = self._settings
        started = time.perf_counter()

        try:
            self.ensure_initialized()
        except (EarthEngineAuthError, ConfigurationError) as exc:
            return {
                "success": False,
                "auth_method": None,
                "project": settings.ee_project,
                "message": exc.message,
                "remediation": self.remediation_steps(),
            }

        try:
            server_number = ee.Number(21).multiply(2).getInfo()

            # A deliberately tiny query: one month, one small box, so the test
            # is fast and cheap even on a cold project.
            probe_geometry = ee.Geometry.Rectangle([75.80, 30.90, 75.85, 30.95])
            probe = (
                ee.ImageCollection(settings.s2_collection_id)
                .filterBounds(probe_geometry)
                .filterDate("2023-11-01", "2023-12-01")
                .limit(5)
            )
            probe_info = ee.Dictionary(
                {
                    "count": probe.size(),
                    "ids": probe.aggregate_array("system:index"),
                }
            ).getInfo()
        except ee.EEException as exc:
            logger.error("Earth Engine connectivity test failed: %s", exc)
            return {
                "success": False,
                "auth_method": self._auth_method,
                "project": settings.ee_project,
                "message": f"Earth Engine rejected the test computation: {exc}",
                "remediation": self.remediation_steps(),
            }

        scene_ids = list((probe_info or {}).get("ids") or [])
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        return {
            "success": True,
            "auth_method": self._auth_method,
            "project": settings.ee_project,
            "round_trip_ms": elapsed_ms,
            "server_side_number": server_number,
            "sample_collection_id": settings.s2_collection_id,
            "sample_scene_count": int((probe_info or {}).get("count") or 0),
            "sample_scene_id": scene_ids[0] if scene_ids else None,
            "message": ("Earth Engine is reachable and the Sentinel-2 collection is queryable."),
            "remediation": [],
        }

    # ------------------------------------------------------------------
    # Evaluation helper
    # ------------------------------------------------------------------
    def evaluate(self, obj: Any, *, label: str = "computation") -> Any:
        """Materialise an Earth Engine object, translating failures.

        Every ``getInfo()`` in CropSense goes through here so that timing is
        logged consistently and Earth Engine's error strings are mapped onto
        domain exceptions.

        Args:
            obj: Any Earth Engine ``ComputedObject``.
            label: Short description used in logs and error messages.

        Returns:
            The evaluated Python value.

        Raises:
            EarthEngineAuthError: The failure looks like a permission problem.
            EarthEngineError: Any other Earth Engine failure.
        """
        self.ensure_initialized()
        started = time.perf_counter()
        try:
            result = obj.getInfo()
        except ee.EEException as exc:
            message = str(exc)
            logger.error("Earth Engine %s failed: %s", label, message)
            lowered = message.lower()
            if any(
                token in lowered
                for token in ("permission", "not authorized", "unauthorized", "forbidden")
            ):
                raise EarthEngineAuthError(
                    f"Earth Engine denied the {label}: {message}",
                    details={"remediation": self.remediation_steps()},
                ) from exc
            raise EarthEngineError(
                f"Earth Engine failed during {label}: {message}",
                details={"label": label},
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected failure during Earth Engine %s", label)
            raise EarthEngineError(
                f"Unexpected failure during {label}: {exc}", details={"label": label}
            ) from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info("Earth Engine %s completed in %d ms", label, elapsed_ms)
        return result

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def build_geometry(self, geojson: dict[str, Any], *, buffer_m: float = 0.0) -> ee.Geometry:
        """Convert a normalised GeoJSON geometry into an ``ee.Geometry``.

        Polygons are treated as planar (``geodesic=False``) so their edges match
        what the user drew on the Web Mercator map rather than being reinterpreted
        as great-circle arcs.

        Args:
            geojson: Geometry dict with ``type`` and ``coordinates`` (EPSG:4326).
            buffer_m: Buffer radius applied to Point geometries, in metres.
                Ignored for polygons.

        Returns:
            The Earth Engine geometry.

        Raises:
            InvalidAOIError: The geometry cannot be constructed, or a Point was
                supplied without a positive buffer.
        """
        self.ensure_initialized()
        geometry_type = geojson.get("type")

        try:
            if geometry_type == "Point":
                if buffer_m <= 0:
                    raise InvalidAOIError(
                        "A Point AOI needs a positive buffer_m to define a field area."
                    )
                geometry = ee.Geometry.Point(geojson["coordinates"]).buffer(buffer_m)
            else:
                geometry = ee.Geometry(geojson, proj="EPSG:4326", geodesic=False)
        except InvalidAOIError:
            raise
        except (ee.EEException, ValueError, TypeError, KeyError) as exc:
            logger.warning("Rejected AOI geometry: %s", exc)
            raise InvalidAOIError(f"Could not build AOI geometry: {exc}") from exc

        return geometry

    def summarize_aoi(self, geometry: ee.Geometry, *, geometry_type: str) -> AOISummary:
        """Measure the AOI and enforce the configured size limit.

        A single Earth Engine round trip returns area, centroid and bounding box.

        Raises:
            InvalidAOIError: The AOI is empty or exceeds ``MAX_AOI_AREA_KM2``.
        """
        payload = ee.Dictionary(
            {
                "area_m2": geometry.area(GEOMETRY_MAX_ERROR_M),
                "centroid": geometry.centroid(GEOMETRY_MAX_ERROR_M).coordinates(),
                "bounds": geometry.bounds(GEOMETRY_MAX_ERROR_M).coordinates(),
            }
        )
        info = self.evaluate(payload, label="AOI measurement")

        area_m2 = float(info.get("area_m2") or 0.0)
        area_km2 = area_m2 / 1_000_000.0
        area_ha = area_m2 / 10_000.0

        if area_m2 <= 0:
            raise InvalidAOIError(
                "The AOI has zero area. Draw a polygon, or use a Point with a buffer."
            )

        limit = self._settings.max_aoi_area_km2
        if area_km2 > limit:
            raise InvalidAOIError(
                f"AOI is {area_km2:,.1f} km2, which exceeds the {limit:,.0f} km2 limit. "
                "Analyse a smaller area, or raise MAX_AOI_AREA_KM2 and increase the "
                "analysis scale.",
                details={"area_km2": round(area_km2, 2), "limit_km2": limit},
            )

        centroid = [float(value) for value in (info.get("centroid") or [0.0, 0.0])]
        bbox = _bbox_from_bounds(info.get("bounds"))

        return AOISummary(
            geometry_type=geometry_type,
            area_ha=round(area_ha, 4),
            area_km2=round(area_km2, 6),
            centroid=[round(value, 6) for value in centroid[:2]],
            bbox=[round(value, 6) for value in bbox],
        )

    # ------------------------------------------------------------------
    # Sentinel-2 collection access
    # ------------------------------------------------------------------
    def build_sentinel2_collection(
        self,
        geometry: ee.Geometry,
        date_range: DateRange,
        cloud_threshold: float,
        *,
        cloud_mask_method: CloudMaskMethod,
        cloud_score_plus_threshold: float | None = None,
    ) -> ee.ImageCollection:
        """Return a cloud-masked, reflectance-scaled Sentinel-2 collection.

        Filtering order matters for cost: bounds and date first (cheap metadata
        filters that drop most of the catalogue), then the scene-level cloud
        percentage, and only then per-pixel masking on what survives.

        The returned images carry scaled float reflectance bands plus a
        ``valid`` band that is 1 where the pixel survived masking. Scene
        metadata (``system:time_start``, ``CLOUDY_PIXEL_PERCENTAGE``, ...) is
        preserved.

        Args:
            geometry: AOI.
            date_range: Inclusive date window. Earth Engine's exclusive end
                bound is handled here.
            cloud_threshold: Maximum scene ``CLOUDY_PIXEL_PERCENTAGE``.
            cloud_mask_method: Per-pixel masking strategy.
            cloud_score_plus_threshold: Cloud Score+ clearness cutoff; defaults
                to the configured value.

        Returns:
            An ``ee.ImageCollection`` sorted ascending by acquisition time.
        """
        self.ensure_initialized()
        settings = self._settings

        # filterDate's end is exclusive; add a day so end_date is included.
        ee_end = (date_range.end_date + timedelta(days=1)).isoformat()

        collection = (
            ee.ImageCollection(settings.s2_collection_id)
            .filterBounds(geometry)
            .filterDate(date_range.start_date.isoformat(), ee_end)
            .filter(ee.Filter.lte(CLOUD_PROPERTY, cloud_threshold))
            .sort("system:time_start")
        )

        if cloud_mask_method is CloudMaskMethod.CS_PLUS:
            threshold = (
                cloud_score_plus_threshold
                if cloud_score_plus_threshold is not None
                else settings.cloud_score_plus_threshold
            )
            collection = self._apply_cloud_score_plus(collection, threshold)
        elif cloud_mask_method is CloudMaskMethod.SCL:
            collection = collection.map(self._mask_with_scl)
        elif cloud_mask_method is CloudMaskMethod.QA60:
            collection = collection.map(self._mask_with_qa60)
        # CloudMaskMethod.NONE: scene-level filtering only.

        return collection.map(self._to_reflectance)

    def _apply_cloud_score_plus(
        self, collection: ee.ImageCollection, threshold: float
    ) -> ee.ImageCollection:
        """Join Cloud Score+ and mask pixels below the clearness threshold.

        Cloud Score+ shares ``system:index`` with the harmonised Sentinel-2
        collection, so ``linkCollection`` joins them without an explicit join.
        The ``cs_cdf`` band is a 0-1 "clearness" score where higher is clearer.
        """
        settings = self._settings
        score_band = settings.cloud_score_plus_band
        score_collection = ee.ImageCollection(settings.cloud_score_plus_collection_id)
        linked = collection.linkCollection(score_collection, [score_band])

        def _mask(image: ee.Image) -> ee.Image:
            clear = image.select(score_band).gte(threshold)
            return image.updateMask(clear)

        return linked.map(_mask)

    def _mask_with_scl(self, image: ee.Image) -> ee.Image:
        """Mask cloud, cirrus, shadow, snow and defective pixels using SCL."""
        scl = image.select(self._settings.band_scl)
        keep = ee.Image.constant(1)
        for value in SCL_MASK_VALUES:
            keep = keep.And(scl.neq(value))
        return image.updateMask(keep)

    def _mask_with_qa60(self, image: ee.Image) -> ee.Image:
        """Mask using the legacy 60 m QA60 opaque-cloud and cirrus bits.

        Coarse (60 m), blind to cloud shadow, and empty for some acquisition
        dates in the harmonised collection. Kept only for reproducing older
        analyses - prefer ``cs_plus`` or ``scl``.
        """
        qa = image.select(self._settings.band_qa60)
        opaque = qa.bitwiseAnd(1 << QA60_OPAQUE_CLOUD_BIT).eq(0)
        cirrus = qa.bitwiseAnd(1 << QA60_CIRRUS_CLOUD_BIT).eq(0)
        return image.updateMask(opaque.And(cirrus))

    def _to_reflectance(self, image: ee.Image) -> ee.Image:
        """Scale integer DN values to physical surface reflectance (0-1).

        NDVI is a normalised ratio and so is invariant to this scaling, but the
        true-colour layer and any future index need real reflectance units.
        Copies scene properties and timestamp onto the result.
        """
        settings = self._settings
        optical = (
            image.select(["B2", "B3", "B4", "B8", "B11", "B12"])
            .multiply(settings.reflectance_scale)
            .toFloat()
        )
        return optical.copyProperties(image, image.propertyNames())

    def collection_metadata(
        self, collection: ee.ImageCollection, *, label: str = "collection metadata"
    ) -> dict[str, Any]:
        """Fetch scene count, IDs, timestamps and cloud percentages in one call.

        Returns:
            ``{"count": int, "ids": [...], "timestamps_ms": [...], "clouds": [...]}``
        """
        payload = ee.Dictionary(
            {
                "count": collection.size(),
                "ids": collection.aggregate_array("system:index"),
                "timestamps_ms": collection.aggregate_array("system:time_start"),
                "clouds": collection.aggregate_array(CLOUD_PROPERTY),
            }
        )
        info = self.evaluate(payload, label=label)
        return {
            "count": int(info.get("count") or 0),
            "ids": list(info.get("ids") or []),
            "timestamps_ms": list(info.get("timestamps_ms") or []),
            "clouds": list(info.get("clouds") or []),
        }

    @staticmethod
    def require_non_empty(
        scene_count: int,
        *,
        date_range: DateRange,
        cloud_threshold: float,
        collection_id: str,
    ) -> None:
        """Raise :class:`NoImageryError` when no scenes survived filtering.

        Zero usable scenes is a normal outcome over cloudy regions, so the
        error message tells the user which knob to turn rather than implying a
        malfunction.
        """
        if scene_count > 0:
            return
        raise NoImageryError(
            "No Sentinel-2 scenes matched this AOI, date range and cloud-cover limit. "
            "Try widening the date range, raising the cloud-cover limit, or checking "
            "that the AOI is on land within Sentinel-2 coverage.",
            details={
                "collection_id": collection_id,
                "start_date": date_range.start_date.isoformat(),
                "end_date": date_range.end_date.isoformat(),
                "cloud_threshold_percent": cloud_threshold,
                "suggestions": [
                    "Extend the date range (cloudy seasons can have no clear scenes for weeks).",
                    "Raise the cloud-cover limit; per-pixel masking still removes cloudy pixels.",
                    "Verify the AOI coordinates are longitude/latitude in EPSG:4326.",
                ],
            },
        )

    # ------------------------------------------------------------------
    # Compositing
    # ------------------------------------------------------------------
    def composite(
        self,
        collection: ee.ImageCollection,
        method: CompositeMethod,
        *,
        quality_band: str | None = None,
    ) -> ee.Image:
        """Reduce a masked collection to a single image.

        Args:
            collection: Cloud-masked collection.
            method: Reduction strategy.
            quality_band: Band maximised by ``CompositeMethod.GREENEST``.
                Required for that method.

        Returns:
            The composited image.

        Raises:
            EarthEngineError: ``greenest`` was requested without a quality band.
        """
        if method is CompositeMethod.MEDIAN:
            return collection.median()
        if method is CompositeMethod.MEAN:
            return collection.mean()
        if method is CompositeMethod.GREENEST:
            if not quality_band:
                raise EarthEngineError("The 'greenest' composite requires a quality band (NDVI).")
            return collection.qualityMosaic(quality_band)
        if method is CompositeMethod.MOST_RECENT:
            # mosaic() paints later images over earlier ones; the collection is
            # sorted ascending by time, so the newest unmasked pixel wins.
            return collection.mosaic()
        raise EarthEngineError(f"Unsupported composite method: {method}")

    # ------------------------------------------------------------------
    # Region reduction
    # ------------------------------------------------------------------
    def reduce_statistics(
        self,
        image: ee.Image,
        geometry: ee.Geometry,
        *,
        band: str,
        scale: int,
    ) -> ee.Dictionary:
        """Build (do not evaluate) a zonal-statistics dictionary for one band.

        Combines mean, min, max, standard deviation and the 10th/50th/90th
        percentiles into a single reducer so Earth Engine walks the pixels once.
        The median is the 50th percentile of the same pass.

        Returns:
            An unevaluated ``ee.Dictionary``. Batch it with other work and pass
            it to :meth:`evaluate`.
        """
        reducer = (
            ee.Reducer.mean()
            .combine(ee.Reducer.minMax(), sharedInputs=True)
            .combine(ee.Reducer.stdDev(), sharedInputs=True)
            .combine(ee.Reducer.percentile([10, 50, 90]), sharedInputs=True)
            .combine(ee.Reducer.count(), sharedInputs=True)
        )
        return image.select([band]).reduceRegion(
            reducer=reducer,
            geometry=geometry,
            scale=scale,
            maxPixels=self._settings.reduce_region_max_pixels,
            bestEffort=False,
        )

    def reduce_valid_area_m2(
        self,
        image: ee.Image,
        geometry: ee.Geometry,
        *,
        band: str,
        scale: int,
    ) -> ee.Number:
        """Build (do not evaluate) the unmasked area of ``band`` within the AOI.

        Uses ``ee.Image.pixelArea()`` rather than a pixel count so partial edge
        pixels contribute proportionally and the result is directly comparable
        with the AOI area.
        """
        valid_area = ee.Image.pixelArea().updateMask(image.select([band]).mask())
        reduced = valid_area.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=scale,
            maxPixels=self._settings.reduce_region_max_pixels,
            bestEffort=False,
        )
        return ee.Number(reduced.get("area"))

    def reduce_area_by_class(
        self,
        class_image: ee.Image,
        geometry: ee.Geometry,
        *,
        class_band: str,
        scale: int,
    ) -> ee.Dictionary:
        """Build (do not evaluate) per-class area and pixel count.

        Stacks ``pixelArea`` (band 0) with the class raster (band 1) and applies
        a grouped reducer, yielding one ``{class, sum, count}`` record per class
        that is present.

        Returns:
            An unevaluated ``ee.Dictionary`` with a ``groups`` list.
        """
        stacked = ee.Image.pixelArea().rename("area").addBands(class_image.select([class_band]))
        grouped = (
            ee.Reducer.sum()
            .combine(ee.Reducer.count(), sharedInputs=True)
            .group(groupField=1, groupName="class")
        )
        return stacked.reduceRegion(
            reducer=grouped,
            geometry=geometry,
            scale=scale,
            maxPixels=self._settings.reduce_region_max_pixels,
            bestEffort=False,
        )

    def reduce_masked_area_m2(
        self,
        mask_image: ee.Image,
        geometry: ee.Geometry,
        *,
        scale: int,
    ) -> ee.Number:
        """Build (do not evaluate) the area where ``mask_image`` is truthy.

        Args:
            mask_image: Single-band image used as a mask (non-zero = included).
        """
        area = ee.Image.pixelArea().updateMask(mask_image)
        reduced = area.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=scale,
            maxPixels=self._settings.reduce_region_max_pixels,
            bestEffort=False,
        )
        return ee.Number(reduced.get("area"))

    # ------------------------------------------------------------------
    # Tile generation
    # ------------------------------------------------------------------
    def get_tile_url_template(
        self, image: ee.Image, vis_params: dict[str, Any], *, label: str = "layer"
    ) -> str:
        """Create a signed XYZ tile URL template for a rendered image.

        ``getMapId`` registers the visualisation server-side and returns an
        ephemeral, signed tile endpoint. The template contains no service
        account key or OAuth token, so it is safe to hand to a browser. It is
        short-lived - re-request it rather than persisting it.

        Args:
            image: Image to render.
            vis_params: Earth Engine visualisation parameters (``min``, ``max``,
                ``palette``, ``bands``).
            label: Used in log and error messages.

        Returns:
            A URL template containing ``{x}``, ``{y}`` and ``{z}`` placeholders.

        Raises:
            EarthEngineError: Tile registration failed.
        """
        self.ensure_initialized()
        try:
            map_id = image.getMapId(vis_params)
        except ee.EEException as exc:
            logger.error("Failed to create tiles for %s: %s", label, exc)
            raise EarthEngineError(
                f"Could not create map tiles for the {label} layer: {exc}",
                details={"layer": label},
            ) from exc

        fetcher = map_id.get("tile_fetcher")
        if fetcher is None or not getattr(fetcher, "url_format", None):
            raise EarthEngineError(
                f"Earth Engine returned no tile URL for the {label} layer.",
                details={"layer": label},
            )
        return str(fetcher.url_format)

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def clip(self, image: ee.Image, geometry: ee.Geometry) -> ee.Image:
        """Clip an image to the AOI so tiles stop at the field boundary."""
        return image.clip(geometry)

    def resolve_scale(self, requested: int | None) -> int:
        """Return the analysis scale in metres, falling back to the default."""
        return int(requested or self._settings.default_analysis_scale_m)

    def cloud_score_plus_supported(self, date_range: DateRange) -> bool:
        """Whether Cloud Score+ covers the whole requested window."""
        return date_range.start_date >= CLOUD_SCORE_PLUS_START


def _bbox_from_bounds(bounds: Any) -> list[float]:
    """Extract ``[min_lon, min_lat, max_lon, max_lat]`` from ee bounds coordinates.

    ``Geometry.bounds()`` returns a polygon ring; we reduce it to a bbox.
    """
    try:
        ring = bounds[0]
        lons = [float(position[0]) for position in ring]
        lats = [float(position[1]) for position in ring]
        return [min(lons), min(lats), max(lons), max(lats)]
    except (TypeError, IndexError, ValueError):  # pragma: no cover - defensive
        logger.warning("Could not derive bbox from bounds payload: %r", bounds)
        return [0.0, 0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------
_service: GEEService | None = None
_service_lock = threading.Lock()


def get_gee_service() -> GEEService:
    """Return the shared :class:`GEEService` (FastAPI dependency)."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = GEEService()
    return _service


def reset_gee_service() -> None:
    """Drop the cached service. Test-support only."""
    global _service
    with _service_lock:
        _service = None
