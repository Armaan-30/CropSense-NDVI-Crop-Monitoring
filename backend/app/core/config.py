"""Application configuration.

All configuration is read from environment variables (optionally via a `.env`
file) using pydantic-settings. Nothing secret is ever hard-coded here.

See `.env.example` at the repository root for the full list of supported
variables and how to obtain them.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Typed application settings.

    Values are resolved with the following precedence:
    1. Real process environment variables.
    2. `backend/.env`
    3. `<repo root>/.env`
    4. The defaults declared below.
    """

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_name: str = "CropSense API"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"
    api_prefix: str = "/api"

    # Comma-separated list, e.g. "http://localhost:5173,http://localhost:3000"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Local persistence for analysed requests/results. SQLite keeps the
    # single-user development setup dependency-free; deployments can point this
    # at a mounted writable volume.
    database_path: str = str(REPO_ROOT / "data" / "cropsense.sqlite3")

    # ------------------------------------------------------------------
    # Google Earth Engine authentication
    # ------------------------------------------------------------------
    # The Google Cloud project that is registered for Earth Engine use.
    # REQUIRED by the Earth Engine v1 API - initialisation fails without it.
    ee_project: str | None = None

    # Preferred for servers: a GCP service account that has been granted
    # Earth Engine access. Provide EITHER a path to the JSON key file OR the
    # raw JSON content (useful for container/secret-manager deployments).
    ee_service_account_email: str | None = None
    ee_service_account_key_file: str | None = None
    ee_service_account_key_json: str | None = None

    # Fallback for local development: use the credentials created by
    # `earthengine authenticate` (stored in ~/.config/earthengine/credentials).
    ee_use_local_credentials: bool = True

    # When no credential *file* exists, let google-auth run its full
    # Application Default Credentials discovery, which includes probing the GCE
    # metadata server. Required when deploying on Google Cloud (Cloud Run, GCE,
    # GKE) where credentials are served by the runtime rather than a file. Keep
    # this False elsewhere: the probe blocks for ~10s before failing.
    ee_allow_adc_discovery: bool = False

    # Earth Engine high-volume endpoint - better suited to many small
    # interactive tile/statistics requests than the default endpoint.
    ee_use_high_volume_endpoint: bool = True

    # Fail fast on startup if Earth Engine cannot be initialised. Keep this
    # False during development so the API (and /health) still boots and can
    # report *why* Earth Engine is unavailable.
    ee_fail_fast: bool = False

    # ------------------------------------------------------------------
    # Sentinel-2 / Earth Engine data configuration
    # ------------------------------------------------------------------
    # Sentinel-2 Level-2A (Surface Reflectance), harmonised across the
    # processing-baseline 04.00 radiometric offset change.
    s2_collection_id: str = "COPERNICUS/S2_SR_HARMONIZED"

    # Google/Cloud Score+ - the currently recommended Sentinel-2 cloud and
    # cloud-shadow assessment product. Used when cloud_mask_method="cs_plus".
    cloud_score_plus_collection_id: str = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
    cloud_score_plus_band: str = "cs_cdf"
    # Keep pixels whose Cloud Score+ "clearness" is above this value.
    # 0.60 is a commonly used starting point; raise it for stricter masking.
    cloud_score_plus_threshold: float = 0.60

    # Band names in the Sentinel-2 SR product.
    band_red: str = "B4"  # Red,  ~665 nm, 10 m
    band_nir: str = "B8"  # NIR,  ~842 nm, 10 m
    band_scl: str = "SCL"  # Scene classification layer, 20 m
    band_qa60: str = "QA60"  # Legacy cloud bitmask, 60 m

    # Surface reflectance is stored as scaled integers (DN = reflectance * 1e4).
    reflectance_scale: float = 1e-4

    # Native analysis scale in metres. 10 m matches B4/B8; increase to trade
    # spatial detail for speed on very large AOIs.
    default_analysis_scale_m: int = 10

    # Guard rails so a single request cannot ask Earth Engine for the world.
    max_aoi_area_km2: float = 2500.0
    max_date_range_days: int = 730
    max_timeseries_points: int = 200

    # `reduceRegion` pixel budget. Earth Engine's default is 1e7.
    reduce_region_max_pixels: int = 10_000_000

    # ------------------------------------------------------------------
    # NDVI health classification thresholds
    # ------------------------------------------------------------------
    # IMPORTANT (scientific caveat):
    # These are *generic* starting points, not universal truths. Absolute NDVI
    # values that indicate a healthy crop depend on crop type, phenological
    # stage, canopy cover, soil background, region, sensor geometry and
    # atmospheric conditions. Calibrate them against ground observations for
    # your own fields before drawing operational conclusions.
    #
    # Interpreted as upper bounds (exclusive) of each class, ascending:
    #   very_low   : ndvi <  t0     (bare soil, water, built-up, senesced)
    #   low        : t0 <= ndvi < t1
    #   moderate   : t1 <= ndvi < t2
    #   healthy    : t2 <= ndvi < t3
    #   very_healthy: ndvi >= t3
    ndvi_class_thresholds: str = "0.2,0.4,0.6,0.8"

    # A same-pixel NDVI drop of at least this magnitude between two periods is
    # flagged as a *potential* stress / significant-decline area. Again: this
    # is a screening threshold, not a diagnosis.
    ndvi_decline_threshold: float = 0.15

    # ------------------------------------------------------------------
    # Validators / derived values
    # ------------------------------------------------------------------
    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        level = value.upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if level not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return level

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list, tolerant of stray whitespace."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_database_path(self) -> Path:
        """Resolve relative database paths against the repository root."""
        path = Path(self.database_path).expanduser()
        return path if path.is_absolute() else (REPO_ROOT / path).resolve()

    @property
    def ndvi_class_threshold_list(self) -> list[float]:
        """The four configured NDVI class boundaries, ascending."""
        raw = [part.strip() for part in self.ndvi_class_thresholds.split(",") if part.strip()]
        if len(raw) != 4:
            raise ValueError(
                "NDVI_CLASS_THRESHOLDS must contain exactly 4 comma-separated numbers "
                f"(got {len(raw)}: {self.ndvi_class_thresholds!r})"
            )
        try:
            thresholds = [float(part) for part in raw]
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"NDVI_CLASS_THRESHOLDS must be numeric: {exc}") from exc
        if thresholds != sorted(thresholds):
            raise ValueError(f"NDVI_CLASS_THRESHOLDS must be strictly ascending (got {thresholds})")
        return thresholds

    @property
    def service_account_key_dict(self) -> dict[str, object] | None:
        """Parsed service-account key JSON, if supplied inline via env var."""
        if not self.ee_service_account_key_json:
            return None
        try:
            parsed = json.loads(self.ee_service_account_key_json)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "EE_SERVICE_ACCOUNT_KEY_JSON is not valid JSON. Provide the full "
                "service-account key file contents, or use "
                "EE_SERVICE_ACCOUNT_KEY_FILE instead."
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError("EE_SERVICE_ACCOUNT_KEY_JSON must decode to a JSON object")
        return parsed

    @property
    def has_service_account_credentials(self) -> bool:
        """True when enough information is present to use a service account."""
        return bool(self.ee_service_account_key_file or self.ee_service_account_key_json)


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()


# Convenience module-level accessor for non-DI call sites.
settings = get_settings()
