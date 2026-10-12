"""API-level tests that run without Earth Engine credentials.

They cover routing, the OpenAPI contract, request validation and the error
envelope - everything except the Earth Engine computation itself.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

VALID_AOI = {
    "type": "Polygon",
    "coordinates": [
        [
            [75.80, 30.90],
            [75.81, 30.90],
            [75.81, 30.91],
            [75.80, 30.91],
            [75.80, 30.90],
        ]
    ],
}


def _analyze_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "aoi": VALID_AOI,
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "cloud_threshold": 30,
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# System endpoints
# ---------------------------------------------------------------------------
def test_root_lists_endpoints(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"]
    assert payload["endpoints"]["analyze"] == "/api/ndvi/analyze"
    assert payload["endpoints"]["health"] == "/health"


def test_health_reports_degraded_without_credentials(client: TestClient) -> None:
    """The API must stay up and explain itself when Earth Engine is unavailable."""
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["earth_engine"]["initialized"] is False
    assert payload["earth_engine"]["remediation"]


def test_health_reports_ok_when_earth_engine_initialised(client: TestClient) -> None:
    from app.api.dependencies import earth_engine_service
    from app.main import app
    from tests.conftest import StubGEEService

    app.dependency_overrides[earth_engine_service] = lambda: StubGEEService(initialized=True)
    try:
        payload = client.get("/health").json()
    finally:
        app.dependency_overrides.clear()

    assert payload["status"] == "ok"
    assert payload["earth_engine"]["initialized"] is True
    assert payload["earth_engine"]["remediation"] == []


def test_config_exposes_defaults_and_no_secrets(client: TestClient) -> None:
    response = client.get("/api/system/config")
    assert response.status_code == 200
    payload = response.json()

    assert payload["collection_id"] == "COPERNICUS/S2_SR_HARMONIZED"
    assert payload["band_red"] == "B4"
    assert payload["band_nir"] == "B8"
    assert payload["default_ndvi_class_thresholds"] == [0.2, 0.4, 0.6, 0.8]
    assert len(payload["health_classes"]) == 5
    assert payload["limitations"]
    assert "calibrate" in payload["calibration_note"].lower()

    # No credential-bearing field may leak through this endpoint.
    serialised = response.text.lower()
    for forbidden in ("private_key", "service_account", "ee_project", "credential"):
        assert forbidden not in serialised


def test_gee_test_reports_failure_without_credentials(client: TestClient) -> None:
    response = client.get("/api/system/gee-test")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["remediation"]


def test_openapi_document_is_generated(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"].startswith("3.1")
    paths = schema["paths"]
    assert "/api/ndvi/analyze" in paths
    assert "/api/ndvi/timeseries" in paths
    assert "/api/ndvi/change" in paths
    assert "/health" in paths


def test_analyze_request_body_example_is_a_valid_example_object(client: TestClient) -> None:
    """Named request examples must land in the OpenAPI Example Object slot.

    Guards a real regression: FastAPI's ``Body(examples=...)`` takes a *list* of
    bare values under OpenAPI 3.1, so passing the ``{name: {"value": ...}}``
    dict there emits a malformed document. The named form belongs to
    ``openapi_examples=``.
    """
    schema = client.get("/openapi.json").json()
    content = schema["paths"]["/api/ndvi/analyze"]["post"]["requestBody"]["content"]
    examples = content["application/json"]["examples"]
    assert "punjab_field" in examples
    example = examples["punjab_field"]
    assert "value" in example, "Example Object must wrap the payload in 'value'"
    assert example["value"]["aoi"]["type"] == "Polygon"


# ---------------------------------------------------------------------------
# Request validation (no Earth Engine call is reached)
# ---------------------------------------------------------------------------
def test_analyze_rejects_reversed_dates(client: TestClient) -> None:
    response = client.post(
        "/api/ndvi/analyze",
        json=_analyze_body(start_date="2024-03-01", end_date="2024-01-01"),
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "validation_error"
    assert payload["details"]["errors"]


def test_analyze_rejects_cloud_threshold_above_100(client: TestClient) -> None:
    response = client.post("/api/ndvi/analyze", json=_analyze_body(cloud_threshold=150))
    assert response.status_code == 422


def test_analyze_rejects_unsupported_geometry(client: TestClient) -> None:
    response = client.post(
        "/api/ndvi/analyze",
        json=_analyze_body(aoi={"type": "LineString", "coordinates": [[0, 0], [1, 1]]}),
    )
    assert response.status_code == 422


def test_analyze_rejects_unknown_option(client: TestClient) -> None:
    """`extra="forbid"` catches typos instead of silently ignoring them."""
    response = client.post(
        "/api/ndvi/analyze",
        json=_analyze_body(options={"cloud_mask_methdo": "cs_plus"}),
    )
    assert response.status_code == 422


def test_analyze_rejects_wrong_threshold_count(client: TestClient) -> None:
    response = client.post(
        "/api/ndvi/analyze",
        json=_analyze_body(options={"ndvi_class_thresholds": [0.2, 0.4, 0.6]}),
    )
    assert response.status_code == 422


def test_analyze_rejects_descending_thresholds(client: TestClient) -> None:
    response = client.post(
        "/api/ndvi/analyze",
        json=_analyze_body(options={"ndvi_class_thresholds": [0.8, 0.6, 0.4, 0.2]}),
    )
    assert response.status_code == 422


def test_analyze_rejects_out_of_range_threshold(client: TestClient) -> None:
    response = client.post(
        "/api/ndvi/analyze",
        json=_analyze_body(options={"ndvi_class_thresholds": [0.2, 0.4, 0.6, 1.5]}),
    )
    assert response.status_code == 422


def test_analyze_rejects_invalid_mask_method(client: TestClient) -> None:
    response = client.post(
        "/api/ndvi/analyze",
        json=_analyze_body(options={"cloud_mask_method": "magic"}),
    )
    assert response.status_code == 422


def test_analyze_returns_503_when_earth_engine_unavailable(client: TestClient) -> None:
    """A valid request must surface a configuration problem, not a 500."""
    response = client.post("/api/ndvi/analyze", json=_analyze_body())
    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "earth_engine_auth_error"
    assert payload["message"]


def test_change_rejects_recent_window_before_baseline(client: TestClient) -> None:
    response = client.post(
        "/api/ndvi/change",
        json={
            "aoi": VALID_AOI,
            "baseline_start_date": "2024-05-01",
            "baseline_end_date": "2024-05-31",
            "recent_start_date": "2024-01-01",
            "recent_end_date": "2024-01-31",
        },
    )
    assert response.status_code == 422


def test_timeseries_rejects_invalid_aggregation(client: TestClient) -> None:
    response = client.post(
        "/api/ndvi/timeseries",
        json={
            "aoi": VALID_AOI,
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "aggregation": "hourly",
        },
    )
    assert response.status_code == 422


def test_timeseries_accepts_valid_aggregations(client: TestClient) -> None:
    """Valid aggregations pass validation and fail later, at the Earth Engine call."""
    for aggregation in ("scene", "weekly", "biweekly", "monthly"):
        response = client.post(
            "/api/ndvi/timeseries",
            json={
                "aoi": VALID_AOI,
                "start_date": "2024-01-01",
                "end_date": "2024-03-31",
                "aggregation": aggregation,
            },
        )
        assert response.status_code == 503, aggregation


def test_cors_headers_present_for_allowed_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
