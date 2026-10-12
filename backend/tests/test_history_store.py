"""SQLite analysis-history persistence tests."""

from __future__ import annotations

import pytest

from app.services.history_store import AnalysisHistoryStore


def test_history_round_trip_and_expiring_tiles_are_not_saved(tmp_path) -> None:
    store = AnalysisHistoryStore(tmp_path / "nested" / "history.sqlite3")
    request = {"start_date": "2026-09-01", "end_date": "2026-09-30"}
    result = {
        "aoi": {"area_ha": 1.25},
        "imagery": {"scene_count": 3},
        "statistics": {"mean": 0.57},
        "layers": [{"id": "ndvi", "tile_url_template": "https://signed/secret-token"}],
    }

    history_id = store.save(mode="snapshot", request=request, result=result)

    entry = store.get(history_id)
    assert entry is not None
    assert entry["request"] == request
    assert entry["result"]["layers"] == [{"id": "ndvi"}]
    assert store.list_recent() == [
        {
            "id": history_id,
            "mode": "snapshot",
            "created_at": entry["created_at"],
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
            "area_ha": 1.25,
            "mean_ndvi": 0.57,
            "scene_count": 3,
        }
    ]
    assert store.delete(history_id)
    assert store.get(history_id) is None
    assert not store.delete(history_id)


def test_history_limit_is_bounded(tmp_path) -> None:
    store = AnalysisHistoryStore(tmp_path / "history.sqlite3")
    with pytest.raises(ValueError, match="between 1 and 100"):
        store.list_recent(limit=0)


def test_history_api_reads_and_deletes_entries(client, history_store) -> None:
    history_id = history_store.save(
        mode="snapshot",
        request={"start_date": "2026-09-01", "end_date": "2026-09-30"},
        result={"statistics": {"mean": 0.51}, "layers": []},
    )

    listed = client.get("/api/history")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == history_id

    detail = client.get(f"/api/history/{history_id}")
    assert detail.status_code == 200
    assert detail.json()["result"]["statistics"]["mean"] == 0.51

    deleted = client.delete(f"/api/history/{history_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/history/{history_id}").status_code == 404


def test_history_api_missing_id_returns_404(client) -> None:
    response = client.get("/api/history/missing")
    assert response.status_code == 404
