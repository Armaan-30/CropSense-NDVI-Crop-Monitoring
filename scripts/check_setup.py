"""Pre-flight check for a CropSense development environment.

Verifies - in order of how likely each is to be the thing that is broken:

1. Python version and required packages.
2. Configuration loaded from ``.env`` (secrets are never printed).
3. Whether Earth Engine credentials exist on disk, and where.
4. Optionally, a real round trip to Earth Engine servers.

Run it from the repository root::

    backend/.venv/Scripts/python.exe scripts/check_setup.py          # Windows
    backend/.venv/bin/python scripts/check_setup.py                  # macOS / Linux

Add ``--live`` to also perform the Earth Engine connectivity test. Without
credentials the script still runs to completion and prints exactly what to
configure; it never invents a working connection.

Exit codes: 0 = ready, 1 = something needs configuring.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

# The backend is not installed as a package, so make `app.*` importable.
sys.path.insert(0, str(BACKEND_DIR))

MIN_PYTHON = (3, 11)

REQUIRED_PACKAGES = (
    "earthengine-api",
    "fastapi",
    "uvicorn",
    "pydantic",
    "pydantic-settings",
    "google-auth",
)

OK = "  [ok]  "
WARN = "  [--]  "
FAIL = "  [!!]  "


def heading(text: str) -> None:
    print(f"\n{text}")
    print("-" * len(text))


def check_python() -> bool:
    """Verify the interpreter is new enough for the syntax the backend uses."""
    heading("1. Python interpreter")
    version = sys.version_info
    pretty = f"{version.major}.{version.minor}.{version.micro}"
    print(f"       executable: {sys.executable}")
    if version >= MIN_PYTHON:
        print(f"{OK}Python {pretty} (>= {MIN_PYTHON[0]}.{MIN_PYTHON[1]} required)")
        return True
    print(
        f"{FAIL}Python {pretty} is too old; {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required"
    )
    return False


def check_packages() -> bool:
    """Verify the runtime dependencies are importable in *this* interpreter."""
    heading("2. Python packages")
    all_present = True
    for name in REQUIRED_PACKAGES:
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            print(f"{FAIL}{name} is not installed")
            all_present = False
        else:
            print(f"{OK}{name} {version}")
    if not all_present:
        print("\n       Fix with:  pip install -r backend/requirements.txt")
    return all_present


def check_configuration() -> tuple[bool, object]:
    """Load settings and report the non-secret values that affect behaviour."""
    heading("3. Configuration")
    try:
        from app.core.config import Settings, get_settings
    except Exception as exc:  # noqa: BLE001 - report any import failure, never traceback
        print(f"{FAIL}Could not import the backend configuration module: {exc}")
        return False, None

    try:
        settings: Settings = get_settings()
    except Exception as exc:  # noqa: BLE001 - any settings error is a reportable finding
        print(f"{FAIL}Configuration failed to load: {exc}")
        print("       Check backend/.env or ./.env against .env.example.")
        return False, None

    env_files = [REPO_ROOT / ".env", BACKEND_DIR / ".env"]
    found_env = [path for path in env_files if path.is_file()]
    if found_env:
        for path in found_env:
            print(f"{OK}Loaded .env from {path}")
    else:
        print(f"{WARN}No .env file found. Copy .env.example to .env and fill it in:")
        print("         cp .env.example .env")

    ok = True
    if settings.ee_project:
        print(f"{OK}EE_PROJECT = {settings.ee_project}")
    else:
        print(
            f"{FAIL}EE_PROJECT is not set - Earth Engine v1 refuses to initialise without it"
        )
        ok = False

    # Report only the *presence* of credentials, never their contents.
    if settings.has_service_account_credentials:
        source = "key file" if settings.ee_service_account_key_file else "inline JSON"
        print(f"{OK}Service-account credentials configured ({source})")
        if settings.ee_service_account_key_file:
            key_path = Path(settings.ee_service_account_key_file).expanduser()
            if key_path.is_file():
                print(f"{OK}Key file exists: {key_path}")
            else:
                print(f"{FAIL}Key file not found: {key_path}")
                ok = False
        if not settings.ee_service_account_email:
            print(
                f"{WARN}EE_SERVICE_ACCOUNT_EMAIL is unset; it is read from the key when omitted"
            )
    else:
        print(f"{WARN}No service account configured (fine for local development)")

    # Try both spellings so a bad NDVI_CLASS_THRESHOLDS value surfaces here
    # rather than on the first analysis request.
    try:
        thresholds = settings.ndvi_class_threshold_list
    except ValueError as exc:
        print(f"{FAIL}NDVI_CLASS_THRESHOLDS is invalid: {exc}")
        ok = False
    else:
        print(
            f"{OK}NDVI class thresholds = {thresholds}  (generic defaults; calibrate locally)"
        )

    print(f"       Sentinel-2 collection: {settings.s2_collection_id}")
    print(f"       Bands: red={settings.band_red}  nir={settings.band_nir}")
    print(f"       CORS origins: {settings.cors_origin_list}")
    return ok, settings


def check_credentials() -> bool:
    """Look for an Earth Engine or ADC credential file on disk."""
    heading("4. Earth Engine credentials on disk")
    try:
        from app.services.gee_service import _local_credential_paths, get_gee_service
    except Exception as exc:  # noqa: BLE001 - report any import failure, never traceback
        print(f"{FAIL}Could not import the Earth Engine service: {exc}")
        return False

    print("       Searched, in order:")
    for path in _local_credential_paths():
        marker = "found" if path.is_file() else "missing"
        print(f"         [{marker:>7}] {path}")

    found = get_gee_service().local_credentials_available()
    if found is not None:
        print(f"{OK}Using credentials at {found}")
        return True

    print(f"{FAIL}No Earth Engine credentials found. Run:")
    print("         earthengine authenticate")
    print(
        "       ...which opens a browser and writes ~/.config/earthengine/credentials."
    )
    return False


def check_live_connection() -> bool:
    """Perform a real, tightly bounded computation on Earth Engine servers."""
    heading("5. Earth Engine live connectivity")
    from app.services.gee_service import get_gee_service

    service = get_gee_service()
    try:
        result = service.connectivity_test()
    except Exception as exc:  # noqa: BLE001 - ee raises many unrelated types on failure
        print(f"{FAIL}Earth Engine is not usable: {exc}")
        for step in service.remediation_steps():
            print(f"         - {step}")
        return False

    if not result.get("success"):
        print(
            f"{FAIL}Earth Engine is not usable: {result.get('message', 'Unknown connection failure')}"
        )
        for step in result.get("remediation") or service.remediation_steps():
            print(f"         - {step}")
        return False

    print(f"{OK}Authenticated via {result.get('auth_method')}")
    print(f"       Round trip: {result.get('round_trip_ms')} ms")
    print(f"       Collection queried: {result.get('sample_collection_id')}")
    print(f"       Scenes found in probe window: {result.get('sample_scene_count')}")
    if result.get("sample_scene_id"):
        print(f"       Example scene: {result['sample_scene_id']}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--live",
        action="store_true",
        help="also contact Earth Engine servers (requires working credentials)",
    )
    args = parser.parse_args()

    print("=" * 72)
    print("CropSense environment check")
    print(f"repository: {REPO_ROOT}")
    print("=" * 72)

    results = {
        "python": check_python(),
        "packages": check_packages(),
    }
    config_ok, _ = check_configuration()
    results["configuration"] = config_ok
    results["credentials"] = check_credentials()

    if args.live:
        if results["credentials"] and results["configuration"]:
            results["connectivity"] = check_live_connection()
        else:
            heading("5. Earth Engine live connectivity")
            print(f"{WARN}Skipped: fix the configuration and credential checks first")
            results["connectivity"] = False
    else:
        heading("5. Earth Engine live connectivity")
        print(f"{WARN}Not attempted. Re-run with --live once credentials are in place.")

    heading("Summary")
    for name, passed in results.items():
        print(f"{OK if passed else FAIL}{name}")

    blocking = [
        name
        for name, passed in results.items()
        if not passed and (name != "connectivity" or args.live)
    ]
    if blocking:
        print(f"\nNot ready yet. Unresolved: {', '.join(blocking)}")
        print("See .env.example and docs/SETUP.md for the full walkthrough.")
        return 1

    print("\nEnvironment looks ready. Start the API with:")
    print("  cd backend && uvicorn app.main:app --reload --port 8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
