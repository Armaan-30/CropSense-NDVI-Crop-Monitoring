"""Small local SQLite repository for analysis history.

The database stores requests and numeric summaries only. Earth Engine tile
URLs are short-lived signed URLs, so they are intentionally removed before a
result is persisted. This repository is for a local, single-user deployment;
add authentication and a server database before exposing it to multiple users.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class AnalysisHistoryStore:
    """Persist NDVI request/result snapshots in a local SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path).expanduser()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Open, transact on, and always close a short-lived connection."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_history (
                    id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL CHECK (mode IN ('snapshot', 'series', 'compare')),
                    created_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_history_created_at "
                "ON analysis_history(created_at DESC)"
            )
            connection.commit()
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _without_expiring_tiles(result: dict[str, Any]) -> dict[str, Any]:
        """Copy a response while excluding short-lived signed map URLs."""
        stored = json.loads(json.dumps(result))
        layers = stored.get("layers")
        if isinstance(layers, list):
            for layer in layers:
                if isinstance(layer, dict):
                    layer.pop("tile_url_template", None)
        return stored

    def save(
        self,
        *,
        mode: str,
        request: dict[str, Any],
        result: dict[str, Any],
    ) -> str:
        """Save one completed analysis and return its opaque history ID."""
        if mode not in {"snapshot", "series", "compare"}:
            raise ValueError(f"Unsupported history mode: {mode}")
        history_id = str(uuid4())
        created_at = datetime.now(UTC).isoformat()
        result_json = self._without_expiring_tiles(result)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO analysis_history (id, mode, created_at, request_json, result_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    history_id,
                    mode,
                    created_at,
                    json.dumps(request, separators=(",", ":")),
                    json.dumps(result_json, separators=(",", ":")),
                ),
            )
        return history_id

    def list_recent(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return summaries for the newest analyses, without full result blobs."""
        if not 1 <= limit <= 100:
            raise ValueError("History limit must be between 1 and 100")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, mode, created_at, request_json, result_json
                FROM analysis_history
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._summary(dict(row)) for row in rows]

    def get(self, history_id: str) -> dict[str, Any] | None:
        """Return a stored request/result pair, if present."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_history WHERE id = ?", (history_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            **self._summary(dict(row)),
            "id": row["id"],
            "mode": row["mode"],
            "created_at": row["created_at"],
            "request": json.loads(row["request_json"]),
            "result": json.loads(row["result_json"]),
        }

    def delete(self, history_id: str) -> bool:
        """Delete one history record; return whether it existed."""
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM analysis_history WHERE id = ?", (history_id,))
            return cursor.rowcount > 0

    @staticmethod
    def _summary(row: dict[str, Any]) -> dict[str, Any]:
        request = json.loads(row["request_json"])
        result = json.loads(row["result_json"])
        stats = result.get("statistics") or {}
        imagery = result.get("imagery") or {}
        aoi = result.get("aoi") or {}
        return {
            "id": row["id"],
            "mode": row["mode"],
            "created_at": row["created_at"],
            "start_date": request.get("start_date") or request.get("baseline_start_date"),
            "end_date": request.get("end_date") or request.get("recent_end_date"),
            "area_ha": aoi.get("area_ha"),
            "mean_ndvi": stats.get("mean"),
            "scene_count": imagery.get("scene_count"),
        }
