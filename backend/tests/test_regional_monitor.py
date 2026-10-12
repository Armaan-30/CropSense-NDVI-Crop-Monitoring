"""Tests for authorized manifest validation and resumable coverage reports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.regional_monitor import RegionalRunStore, load_fields

FIELD_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [
        [[75.55, 21.0], [75.551, 21.0], [75.551, 21.001], [75.55, 21.001], [75.55, 21.0]]
    ],
}


def _write_manifest(
    path: Path, *, geometry: dict | None = None, field_id: str = "field-001"
) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "field_id": field_id,
                            "cultivated_area_ha": 2.5,
                            "crop_type": "cotton",
                            "season": "kharif-2026",
                        },
                        "geometry": geometry or FIELD_GEOMETRY,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_load_fields_requires_stable_id_area_and_closed_supported_geometry(tmp_path: Path) -> None:
    manifest = tmp_path / "fields.geojson"
    _write_manifest(manifest)
    fields = load_fields(manifest)

    assert fields[0]["field_id"] == "field-001"
    assert fields[0]["cultivated_area_ha"] == 2.5
    assert len(fields[0]["geometry_sha256"]) == 64

    open_ring = {
        "type": "Polygon",
        "coordinates": [[[75.55, 21.0], [75.551, 21.0], [75.551, 21.001], [75.55, 21.001]]],
    }
    _write_manifest(manifest, geometry=open_ring)
    with pytest.raises(ValueError, match="not closed"):
        load_fields(manifest)


def test_load_fields_rejects_duplicate_ids_and_missing_area(tmp_path: Path) -> None:
    manifest = tmp_path / "fields.geojson"
    _write_manifest(manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["features"].append(payload["features"][0])
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate field_id"):
        load_fields(manifest)

    payload["features"] = [payload["features"][0]]
    del payload["features"][0]["properties"]["cultivated_area_ha"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="cultivated_area_ha"):
        load_fields(manifest)


def test_load_fields_accepts_geopackage_and_selects_layer(tmp_path: Path) -> None:
    fiona = pytest.importorskip("fiona")

    path = tmp_path / "authorized-fields.gpkg"
    schema = {
        "geometry": "Polygon",
        "properties": {
            "field_id": "str",
            "cultivated_area_ha": "float",
            "crop_type": "str",
            "season": "str",
        },
    }
    with fiona.open(
        path,
        mode="w",
        driver="GPKG",
        layer="farm_boundaries",
        crs="EPSG:4326",
        schema=schema,
    ) as sink:
        sink.write(
            {
                "geometry": FIELD_GEOMETRY,
                "properties": {
                    "field_id": "field-gpkg-1",
                    "cultivated_area_ha": 2.5,
                    "crop_type": "cotton",
                    "season": "kharif-2026",
                },
            }
        )

    fields = load_fields(path, layer="farm_boundaries")
    assert fields[0]["field_id"] == "field-gpkg-1"
    assert fields[0]["cultivated_area_ha"] == 2.5
    assert fields[0]["geometry"]["type"] == "Polygon"


def test_report_separates_processed_hectares_from_cloud_valid_hectares(tmp_path: Path) -> None:
    manifest = tmp_path / "fields.geojson"
    _write_manifest(manifest)
    field = load_fields(manifest)[0]
    store = RegionalRunStore(tmp_path / "regional.sqlite3")
    store.create_run(
        run_id="pilot-1",
        metadata={
            "region": "Jalgaon pilot",
            "dataset_name": "authorized field register",
            "dataset_release": "2026-10",
            "dataset_license": "pilot permission",
            "authorization_reference": "approval-123",
            "denominator_ha": 100.0,
            "denominator_basis": "net_sown",
            "denominator_source": "official cultivated-area table",
            "denominator_as_of": "2026-10-01",
            "season": "kharif-2026",
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
            "cloud_threshold": 30.0,
            "target_fraction": 1.0,
            "non_overlapping_boundaries": True,
        },
        fields=[field],
    )
    store.mark_running("pilot-1")
    store.save_result(
        run_id="pilot-1",
        field_id=field["field_id"],
        geometry_sha256=field["geometry_sha256"],
        state="complete",
        scene_count=3,
        mean_ndvi=0.42,
        valid_pixel_fraction=0.6,
        usable_area_ha=1.5,
        duration_ms=1250,
        warnings=["Test quality note"],
    )
    store.finish_run("pilot-1")

    report = store.report("pilot-1")
    assert report["state"] == "complete"
    assert report["target"]["processed_area_ha"] == 2.5
    assert report["target"]["cloud_valid_area_ha"] == 1.5
    assert report["target"]["processed_percent"] == 2.5
    assert report["target"]["cloud_valid_percent"] == 1.5
    assert report["fields"][0]["duration_ms"] == 1250
    assert report["runtime_observations"]["sample_count"] == 1
    assert report["runtime_observations"]["total_ms"] == 1250
    assert "not Earth Engine EECU usage" in report["runtime_observations"]["scope"]
    assert report["accuracy"] is None


def test_batch_checkpoints_success_and_can_resume(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from app.services.regional_monitor import _execute_batch

    manifest = tmp_path / "fields.geojson"
    _write_manifest(manifest)
    field = load_fields(manifest)[0]
    store = RegionalRunStore(tmp_path / "regional.sqlite3")
    store.create_run(
        run_id="pilot-2",
        metadata={
            "region": "pilot",
            "dataset_name": "authorized",
            "dataset_release": "v1",
            "dataset_license": "permission",
            "authorization_reference": "ref",
            "denominator_ha": 100.0,
            "denominator_basis": "net_sown",
            "denominator_source": "source",
            "denominator_as_of": "2026-10-01",
            "season": "kharif",
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
            "cloud_threshold": 30.0,
            "target_fraction": 1.0,
            "non_overlapping_boundaries": True,
        },
        fields=[field],
    )

    class ModelPayload(SimpleNamespace):
        def model_dump(self, *, mode: str) -> dict:
            assert mode == "json"
            return self.payload

    fake_response = SimpleNamespace(
        statistics=SimpleNamespace(valid_pixel_fraction=0.8, mean=0.5),
        imagery=ModelPayload(scene_count=4, payload={"scene_count": 4}),
        health=ModelPayload(payload={"thresholds_source": "server_default"}),
        warnings=[],
        notes=[],
        duration_ms=50,
    )
    fake_response.statistics = ModelPayload(
        valid_pixel_fraction=0.8,
        mean=0.5,
        payload={"valid_pixel_fraction": 0.8, "mean": 0.5},
    )
    _execute_batch(
        store,
        "pilot-2",
        [field],
        max_fields=1,
        analyze=lambda _field, _metadata: fake_response,
    )
    assert store.report("pilot-2")["state"] == "complete"
    assert store.report("pilot-2")["fields"][0]["imagery"] == {"scene_count": 4}
    assert store.report("pilot-2")["fields"][0]["duration_ms"] == 50
    assert store.next_fields("pilot-2", 1) == []
