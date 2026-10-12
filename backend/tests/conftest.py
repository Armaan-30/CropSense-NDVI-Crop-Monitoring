"""Shared pytest fixtures.

Tests must never require Earth Engine credentials or network access. The Earth
Engine service is therefore stubbed by default - both as the FastAPI dependency
and as the process-wide singleton the application lifespan reaches for - and the
small number of tests that need a live connection are marked ``integration`` and
skipped unless ``CROPSENSE_RUN_INTEGRATION=1``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

RUN_INTEGRATION = os.environ.get("CROPSENSE_RUN_INTEGRATION") == "1"

# Keep unit-test settings deterministic, but let integration runs use the real
# project and credentials from the user's environment / repository .env.
if not RUN_INTEGRATION:
    os.environ.setdefault("EE_PROJECT", "test-project")
    os.environ.setdefault("EE_FAIL_FAST", "false")
    os.environ.setdefault("EE_ALLOW_ADC_DISCOVERY", "false")
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    os.environ.setdefault("NDVI_CLASS_THRESHOLDS", "0.2,0.4,0.6,0.8")

requires_earth_engine = pytest.mark.skipif(
    not RUN_INTEGRATION,
    reason="Set CROPSENSE_RUN_INTEGRATION=1 and configure Earth Engine credentials to run.",
)


class StubGEEService:
    """Minimal stand-in for :class:`app.services.gee_service.GEEService`.

    Reports Earth Engine as unavailable so route wiring, validation and error
    envelopes can be tested without credentials. Any Earth Engine operation not
    defined here raises :class:`EarthEngineAuthError` through
    :meth:`__getattr__`, which is exactly how the real service behaves when it
    cannot authenticate - so a route that forgets to handle that path shows up
    as a 503, never a 500.
    """

    def __init__(self, *, initialized: bool = False) -> None:
        self._initialized = initialized
        self.calls: list[str] = []

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(self, *, force: bool = False) -> None:
        self.calls.append("initialize")
        if not self._initialized:
            raise self._error()

    def ensure_initialized(self) -> None:
        self.initialize()

    def remediation_steps(self) -> list[str]:
        return ["stub remediation step"]

    def status(self) -> dict[str, Any]:
        if self._initialized:
            return {
                "initialized": True,
                "auth_method": "service_account",
                "project": "test-project",
                "service_account_email": None,
                "high_volume_endpoint": True,
                "error": None,
                "remediation": [],
            }
        return {
            "initialized": False,
            "auth_method": None,
            "project": "test-project",
            "service_account_email": None,
            "high_volume_endpoint": True,
            "error": "stub: no credentials configured",
            "remediation": self.remediation_steps(),
        }

    def connectivity_test(self) -> dict[str, Any]:
        return {
            "success": False,
            "auth_method": None,
            "project": "test-project",
            "message": "stub: no credentials configured",
            "remediation": self.remediation_steps(),
        }

    @staticmethod
    def _error() -> Exception:
        from app.core.exceptions import EarthEngineAuthError

        return EarthEngineAuthError(
            "stub: no credentials configured",
            details={"remediation": ["stub remediation step"]},
        )

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        def _unavailable(*args: Any, **kwargs: Any) -> Any:
            raise StubGEEService._error()

        return _unavailable


@pytest.fixture(scope="session", autouse=True)
def _no_live_earth_engine() -> Iterator[None]:
    """Replace the process-wide Earth Engine singleton with the stub.

    The FastAPI lifespan and any module-level factory call
    ``get_gee_service()`` directly, bypassing dependency overrides. Without this
    fixture every ``TestClient(app)`` would attempt a real authentication and
    block for ~10s on Google's metadata server.
    """
    if RUN_INTEGRATION:
        # The opt-in integration test deliberately exercises the real singleton.
        yield
        return

    from app.services import gee_service

    gee_service._service = StubGEEService()  # type: ignore[assignment]
    yield
    gee_service.reset_gee_service()


@pytest.fixture
def stub_gee() -> StubGEEService:
    """An Earth Engine stub that reports itself unavailable."""
    return StubGEEService()


@pytest.fixture
def history_store(tmp_path: Any) -> Any:
    """An isolated SQLite store for each API test."""
    from app.services.history_store import AnalysisHistoryStore

    return AnalysisHistoryStore(tmp_path / "history.sqlite3")


@pytest.fixture
def client(stub_gee: StubGEEService, history_store: Any) -> Iterator[TestClient]:
    """A TestClient whose Earth Engine dependency is replaced by the stub."""
    from app.api.dependencies import analysis_history_store, earth_engine_service
    from app.main import app

    app.dependency_overrides[earth_engine_service] = lambda: stub_gee
    app.dependency_overrides[analysis_history_store] = lambda: history_store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
