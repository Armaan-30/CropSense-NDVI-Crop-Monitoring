"""Run a bounded, resumable NDVI monitor over authorized GeoJSON/GeoPackage fields.

This is an operator tool, not an unattended state-wide scheduler. A run stores
only non-personal field IDs, geometry hashes, measurements, and provenance.
Each field is analyzed serially and checkpointed so a stopped run can resume.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import sqlite3
import sys
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.core.exceptions import (
    ConfigurationError,
    CropSenseError,
    EarthEngineAuthError,
    NoImageryError,
)
from app.schemas.aoi import GeoJSONGeometry

REPO_ROOT = Path(__file__).resolve().parents[3]
MAX_FIELDS_PER_BATCH = 25
MAX_PILOT_FEATURES = 50_000


def load_fields(path: Path, *, layer: str | None = None) -> list[dict[str, Any]]:
    """Load and validate authorized GeoJSON or GeoPackage field boundaries.

    Each feature must carry a stable ``field_id`` and a source-provided
    ``cultivated_area_ha`` for this land parcel. Crop names are metadata only;
    they are never sent to Earth Engine or used to claim crop identification.
    """
    if path.suffix.lower() in {".gpkg", ".geopackage"}:
        try:
            import fiona
            from fiona.errors import FionaError
            from fiona.transform import transform_geom
        except ImportError as exc:
            raise ValueError(
                "GeoPackage input requires Fiona, which is not installed for this Python "
                "version. Use the Python 3.12 Docker runtime or a Python 3.11-3.13 "
                "environment with backend requirements installed; alternatively, export "
                "the authorized layer as GeoJSON."
            ) from exc
        try:
            layers = fiona.listlayers(path)
            if not layers:
                raise ValueError("GeoPackage contains no vector layers.")
            selected_layer = layer or layers[0]
            if selected_layer not in layers:
                raise ValueError(
                    f"Layer {selected_layer!r} not found in GeoPackage. Available: {layers}"
                )
            with fiona.open(path, layer=selected_layer) as source:
                source_crs = source.crs_wkt or source.crs
                if not source_crs:
                    raise ValueError("GeoPackage layer has no declared coordinate system.")
                geopackage_features = []
                for feature in source:
                    geometry = feature.get("geometry")
                    if geometry is not None:
                        geometry = transform_geom(source_crs, "EPSG:4326", geometry)
                    geopackage_features.append(
                        {
                            "type": "Feature",
                            "properties": dict(feature.get("properties") or {}),
                            "geometry": geometry,
                        }
                    )
            payload = {"type": "FeatureCollection", "features": geopackage_features}
        except (FionaError, OSError, ValueError) as exc:
            raise ValueError(f"Cannot read valid GeoPackage from {path}: {exc}") from exc
    else:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read valid UTF-8 GeoJSON from {path}: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("Input must be a GeoJSON FeatureCollection.")
    feature_list = payload.get("features")
    if not isinstance(feature_list, list) or not feature_list:
        raise ValueError("FeatureCollection must contain at least one field feature.")
    if len(feature_list) > MAX_PILOT_FEATURES:
        raise ValueError(
            f"Pilot input has {len(feature_list):,} features; limit is {MAX_PILOT_FEATURES:,}. "
            "Partition the authorized dataset into smaller pilot manifests."
        )

    output: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, feature in enumerate(feature_list):
        label = f"features[{index}]"
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"{label} must be a GeoJSON Feature.")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict):
            raise ValueError(f"{label}.properties must be an object.")
        field_id = properties.get("field_id")
        if not isinstance(field_id, str) or not field_id.strip():
            raise ValueError(f"{label}.properties.field_id must be a non-empty stable string.")
        field_id = field_id.strip()
        if field_id in seen_ids:
            raise ValueError(f"Duplicate field_id {field_id!r}; input IDs must be unique.")
        seen_ids.add(field_id)

        try:
            parsed_geometry = GeoJSONGeometry.model_validate(geometry)
        except ValidationError as exc:
            raise ValueError(f"{label}.geometry is invalid: {exc}") from exc
        if parsed_geometry.type not in {"Polygon", "MultiPolygon"}:
            raise ValueError(f"{label} must be a Polygon or MultiPolygon field boundary.")
        _require_closed_rings(parsed_geometry.to_dict(), label)

        try:
            area_ha = float(properties["cultivated_area_ha"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"{label}.properties.cultivated_area_ha must be supplied by the authorized source."
            ) from exc
        if not math.isfinite(area_ha) or area_ha <= 0:
            raise ValueError(f"{label}.properties.cultivated_area_ha must be positive and finite.")

        crop_type = properties.get("crop_type")
        season = properties.get("season")
        output.append(
            {
                "field_id": field_id,
                "geometry": parsed_geometry.to_dict(),
                "geometry_sha256": hashlib.sha256(
                    json.dumps(
                        parsed_geometry.to_dict(), sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")
                ).hexdigest(),
                "cultivated_area_ha": area_ha,
                "crop_type": crop_type.strip() if isinstance(crop_type, str) else None,
                "season": season.strip() if isinstance(season, str) else None,
            }
        )
    return output


def _require_closed_rings(geometry: dict[str, Any], label: str) -> None:
    """Reject unclosed polygon rings; GeoJSON's minimum vertex count isn't enough."""
    coordinates = geometry["coordinates"]
    polygons = [coordinates] if geometry["type"] == "Polygon" else coordinates
    for polygon_index, polygon in enumerate(polygons):
        for ring_index, ring in enumerate(polygon):
            if ring[0][:2] != ring[-1][:2]:
                raise ValueError(
                    f"{label} polygon[{polygon_index}] ring[{ring_index}] is not closed."
                )


class RegionalRunStore:
    """SQLite checkpoint store for one bounded regional pilot run."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS regional_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                region TEXT NOT NULL,
                dataset_name TEXT NOT NULL,
                dataset_release TEXT NOT NULL,
                dataset_license TEXT NOT NULL,
                authorization_reference TEXT NOT NULL,
                denominator_ha REAL NOT NULL,
                denominator_basis TEXT NOT NULL DEFAULT 'unspecified',
                denominator_source TEXT NOT NULL,
                denominator_as_of TEXT NOT NULL,
                season TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                cloud_threshold REAL NOT NULL,
                target_fraction REAL NOT NULL,
                non_overlapping_boundaries INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS regional_field_results (
                run_id TEXT NOT NULL REFERENCES regional_runs(run_id) ON DELETE CASCADE,
                field_id TEXT NOT NULL,
                geometry_sha256 TEXT NOT NULL,
                cultivated_area_ha REAL NOT NULL,
                crop_type TEXT,
                field_season TEXT,
                state TEXT NOT NULL,
                scene_count INTEGER,
                mean_ndvi REAL,
                valid_pixel_fraction REAL,
                usable_area_ha REAL,
                duration_ms INTEGER,
                warnings_json TEXT NOT NULL DEFAULT '[]',
                error TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (run_id, field_id, geometry_sha256)
            )
            """
        )
        run_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(regional_runs)").fetchall()
        }
        if "non_overlapping_boundaries" not in run_columns:
            connection.execute(
                "ALTER TABLE regional_runs ADD COLUMN non_overlapping_boundaries "
                "INTEGER NOT NULL DEFAULT 0"
            )
        if "denominator_basis" not in run_columns:
            connection.execute(
                "ALTER TABLE regional_runs ADD COLUMN denominator_basis "
                "TEXT NOT NULL DEFAULT 'unspecified'"
            )
        self._migrate_result_columns(connection)
        connection.commit()
        return connection

    @staticmethod
    def _migrate_result_columns(connection: sqlite3.Connection) -> None:
        """Add provenance fields to a pilot database created by an earlier version."""
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(regional_field_results)").fetchall()
        }
        additions = {
            "imagery_json": "TEXT",
            "statistics_json": "TEXT",
            "health_json": "TEXT",
            "notes_json": "TEXT NOT NULL DEFAULT '[]'",
            "duration_ms": "INTEGER",
        }
        for name, declaration in additions.items():
            if name not in existing:
                connection.execute(
                    f"ALTER TABLE regional_field_results ADD COLUMN {name} {declaration}"
                )

    def create_run(
        self, *, run_id: str, metadata: dict[str, Any], fields: Sequence[dict[str, Any]]
    ) -> None:
        """Create run metadata and queued field rows atomically."""
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO regional_runs (
                    run_id, created_at, updated_at, region, dataset_name, dataset_release,
                    dataset_license, authorization_reference, denominator_ha,
                    denominator_basis, denominator_source, denominator_as_of, season,
                    start_date, end_date,
                    cloud_threshold, target_fraction, non_overlapping_boundaries, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued')""",
                (
                    run_id,
                    now,
                    now,
                    metadata["region"],
                    metadata["dataset_name"],
                    metadata["dataset_release"],
                    metadata["dataset_license"],
                    metadata["authorization_reference"],
                    metadata["denominator_ha"],
                    metadata["denominator_basis"],
                    metadata["denominator_source"],
                    metadata["denominator_as_of"],
                    metadata["season"],
                    metadata["start_date"],
                    metadata["end_date"],
                    metadata["cloud_threshold"],
                    metadata["target_fraction"],
                    int(metadata["non_overlapping_boundaries"]),
                ),
            )
            connection.executemany(
                """INSERT INTO regional_field_results (
                    run_id, field_id, geometry_sha256, cultivated_area_ha, crop_type,
                    field_season, state, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'queued', ?)""",
                [
                    (
                        run_id,
                        field["field_id"],
                        field["geometry_sha256"],
                        field["cultivated_area_ha"],
                        field["crop_type"],
                        field["season"],
                        now,
                    )
                    for field in fields
                ],
            )

    def run_metadata(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM regional_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return dict(row) if row else None

    def next_fields(self, run_id: str, limit: int) -> list[dict[str, Any]]:
        """Atomically claim the next queued fields so parallel runs can't duplicate work."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """SELECT field_id, geometry_sha256, cultivated_area_ha
                   FROM regional_field_results
                   WHERE run_id = ? AND state IN ('queued', 'failed')
                   ORDER BY field_id LIMIT ?""",
                (run_id, limit),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """UPDATE regional_field_results SET state = 'processing', updated_at = ?
                       WHERE run_id = ? AND field_id = ? AND geometry_sha256 = ?""",
                    (_now(), run_id, row["field_id"], row["geometry_sha256"]),
                )
        return [dict(row) for row in rows]

    def requeue_interrupted_fields(self, run_id: str) -> None:
        """Recover fields left in `processing` by a crashed previous invocation."""
        with self._connect() as connection:
            connection.execute(
                """UPDATE regional_field_results SET state = 'queued', updated_at = ?
                   WHERE run_id = ? AND state = 'processing'""",
                (_now(), run_id),
            )

    def mark_running(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE regional_runs SET state = 'running', updated_at = ? WHERE run_id = ?",
                (_now(), run_id),
            )

    def save_result(
        self,
        *,
        run_id: str,
        field_id: str,
        geometry_sha256: str,
        state: str,
        scene_count: int | None = None,
        mean_ndvi: float | None = None,
        valid_pixel_fraction: float | None = None,
        usable_area_ha: float | None = None,
        duration_ms: int | None = None,
        imagery: dict[str, Any] | None = None,
        statistics: dict[str, Any] | None = None,
        health: dict[str, Any] | None = None,
        notes: Sequence[str] = (),
        warnings: Sequence[str] = (),
        error: str | None = None,
    ) -> None:
        if state not in {"complete", "no_imagery", "failed"}:
            raise ValueError(f"Unsupported field result state: {state}")
        with self._connect() as connection:
            connection.execute(
                """UPDATE regional_field_results SET state = ?, scene_count = ?, mean_ndvi = ?,
                    valid_pixel_fraction = ?, usable_area_ha = ?, duration_ms = ?, imagery_json = ?,
                    statistics_json = ?, health_json = ?, notes_json = ?, warnings_json = ?,
                    error = ?, updated_at = ? WHERE run_id = ? AND field_id = ?
                    AND geometry_sha256 = ?""",
                (
                    state,
                    scene_count,
                    mean_ndvi,
                    valid_pixel_fraction,
                    usable_area_ha,
                    duration_ms,
                    json.dumps(imagery) if imagery is not None else None,
                    json.dumps(statistics) if statistics is not None else None,
                    json.dumps(health) if health is not None else None,
                    json.dumps(list(notes)),
                    json.dumps(list(warnings)),
                    error[:1000] if error else None,
                    _now(),
                    run_id,
                    field_id,
                    geometry_sha256,
                ),
            )

    def finish_run(self, run_id: str) -> None:
        with self._connect() as connection:
            pending = connection.execute(
                """SELECT COUNT(*) AS count FROM regional_field_results
                   WHERE run_id = ? AND state IN ('queued', 'failed', 'processing')""",
                (run_id,),
            ).fetchone()["count"]
            state = "paused" if pending else "complete"
            connection.execute(
                "UPDATE regional_runs SET state = ?, updated_at = ? WHERE run_id = ?",
                (state, _now(), run_id),
            )

    def report(self, run_id: str) -> dict[str, Any]:
        metadata = self.run_metadata(run_id)
        if metadata is None:
            raise ValueError(f"Unknown regional run ID: {run_id}")
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT state, COUNT(*) AS field_count,
                          SUM(cultivated_area_ha) AS area_ha,
                          SUM(COALESCE(usable_area_ha, 0)) AS usable_area_ha
                   FROM regional_field_results WHERE run_id = ? GROUP BY state""",
                (run_id,),
            ).fetchall()
            results = connection.execute(
                """SELECT field_id, state, cultivated_area_ha, scene_count, mean_ndvi,
                          valid_pixel_fraction, usable_area_ha, duration_ms, imagery_json,
                          statistics_json, health_json, notes_json, warnings_json, error
                   FROM regional_field_results WHERE run_id = ? ORDER BY field_id""",
                (run_id,),
            ).fetchall()

        by_state = {row["state"]: dict(row) for row in rows}
        completed_area = float(by_state.get("complete", {}).get("area_ha") or 0.0)
        no_imagery_area = float(by_state.get("no_imagery", {}).get("area_ha") or 0.0)
        failed_area = float(by_state.get("failed", {}).get("area_ha") or 0.0)
        usable_area = sum(float(row["usable_area_ha"] or 0.0) for row in results)
        measured_durations = [
            int(row["duration_ms"])
            for row in results
            if row["duration_ms"] is not None and row["state"] == "complete"
        ]
        denominator = float(metadata["denominator_ha"])
        target_area = denominator * float(metadata["target_fraction"])
        fields = [
            {
                "field_id": row["field_id"],
                "state": row["state"],
                "cultivated_area_ha": row["cultivated_area_ha"],
                "scene_count": row["scene_count"],
                "mean_ndvi": row["mean_ndvi"],
                "valid_pixel_fraction": row["valid_pixel_fraction"],
                "usable_area_ha": row["usable_area_ha"],
                "duration_ms": row["duration_ms"],
                "imagery": json.loads(row["imagery_json"]) if row["imagery_json"] else None,
                "statistics": json.loads(row["statistics_json"])
                if row["statistics_json"]
                else None,
                "health": json.loads(row["health_json"]) if row["health_json"] else None,
                "notes": json.loads(row["notes_json"]),
                "warnings": json.loads(row["warnings_json"]),
                "error": row["error"],
            }
            for row in results
        ]
        return {
            "run_id": run_id,
            "state": metadata["state"],
            "updated_at": metadata["updated_at"],
            "region": metadata["region"],
            "season": metadata["season"],
            "date_window": {"start": metadata["start_date"], "end": metadata["end_date"]},
            "dataset": {
                "name": metadata["dataset_name"],
                "release": metadata["dataset_release"],
                "license": metadata["dataset_license"],
                "authorization_reference": metadata["authorization_reference"],
            },
            "denominator": {
                "cultivated_area_ha": denominator,
                "basis": metadata["denominator_basis"],
                "source": metadata["denominator_source"],
                "as_of": metadata["denominator_as_of"],
            },
            "target": {
                "fraction": metadata["target_fraction"],
                "area_ha": target_area,
                "processed_area_ha": completed_area,
                "attempted_area_ha": completed_area + no_imagery_area + failed_area,
                "cloud_valid_area_ha": usable_area,
                "processed_percent": min(100.0, completed_area / denominator * 100),
                "cloud_valid_percent": min(100.0, usable_area / denominator * 100),
                "target_met": usable_area / denominator >= float(metadata["target_fraction"]),
            },
            "field_counts": {
                state: int(values["field_count"]) for state, values in by_state.items()
            },
            "areas_by_state_ha": {
                state: float(values["area_ha"] or 0.0) for state, values in by_state.items()
            },
            "fields": fields,
            "runtime_observations": {
                "scope": "successful per-field server processing time; not Earth Engine EECU usage",
                "sample_count": len(measured_durations),
                "total_ms": sum(measured_durations),
                "mean_ms": (
                    round(sum(measured_durations) / len(measured_durations))
                    if measured_durations
                    else None
                ),
                "max_ms": max(measured_durations) if measured_durations else None,
            },
            "accuracy": None,
            "accuracy_note": (
                "NDVI accuracy requires independent field observations; none are inferred here."
            ),
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


@contextlib.contextmanager
def _exclusive_run_lock(store: RegionalRunStore, run_id: str) -> Iterator[None]:
    """Take a cross-platform process lock for one run; the OS releases it on exit/crash."""
    token = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:20]
    lock_path = store.path.with_name(f"{store.path.name}.{token}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        try:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0)
                if lock_file.read(1) == b"":
                    lock_file.seek(0)
                    lock_file.write(b"0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(  # type: ignore[attr-defined]  # POSIX-only branch; Windows uses msvcrt.
                    lock_file.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,  # type: ignore[attr-defined]
                )
        except OSError as exc:
            raise RuntimeError(
                "This regional run is already active in another process. "
                "Wait for it to finish before resuming."
            ) from exc
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(  # type: ignore[attr-defined]  # POSIX-only branch; Windows uses msvcrt.
                    lock_file.fileno(),
                    fcntl.LOCK_UN,  # type: ignore[attr-defined]
                )


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Date must be YYYY-MM-DD.") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "field_dataset",
        type=Path,
        help="Authorized GeoJSON FeatureCollection or GeoPackage (.gpkg; first layer used)",
    )
    parser.add_argument(
        "--layer", help="GeoPackage layer name (defaults to its first vector layer)"
    )
    parser.add_argument("--region", required=True, help="Pilot region, e.g. district/taluka")
    parser.add_argument("--season", required=True, help="Season label for this field dataset")
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--dataset-release", required=True, help="Release/date/version identifier")
    parser.add_argument("--dataset-license", required=True, help="License or terms of use")
    parser.add_argument(
        "--authorization-reference",
        required=True,
        help="Non-personal approval, consent, agreement or API access reference",
    )
    parser.add_argument("--denominator-ha", type=float, required=True)
    parser.add_argument(
        "--denominator-basis",
        choices=("net_sown", "gross_cropped", "other"),
        required=True,
        help="Area definition; field hectares and denominator must use the same basis",
    )
    parser.add_argument("--denominator-source", required=True)
    parser.add_argument("--denominator-as-of", type=_parse_date, required=True)
    parser.add_argument("--start-date", type=_parse_date, required=True)
    parser.add_argument("--end-date", type=_parse_date, required=True)
    parser.add_argument("--cloud-threshold", type=float, default=30.0)
    parser.add_argument(
        "--target-fraction",
        type=float,
        default=1.0,
        help="Coverage goal as a fraction of cultivated hectares (default: 1.0 = 100%%)",
    )
    parser.add_argument(
        "--max-fields",
        type=int,
        required=True,
        help=f"Maximum new field attempts this invocation (1-{MAX_FIELDS_PER_BATCH})",
    )
    parser.add_argument("--db", type=Path, default=Path("data/regional-monitoring.sqlite3"))
    parser.add_argument("--report-out", type=Path, help="Write the JSON coverage report here")
    parser.add_argument("--run-id", help="Resume this saved run instead of creating one")
    parser.add_argument(
        "--authorized-data",
        action="store_true",
        required=True,
        help="Confirm the source is licensed and its use is authorized",
    )
    parser.add_argument(
        "--non-overlapping-boundaries",
        action="store_true",
        required=True,
        help="Confirm field geometries do not overlap and hectares are not double-counted",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.end_date < args.start_date:
        parser.error("--end-date must be on or after --start-date")
    if args.denominator_ha <= 0 or not math.isfinite(args.denominator_ha):
        parser.error("--denominator-ha must be positive and finite")
    if not 0 < args.target_fraction <= 1:
        parser.error("--target-fraction must be greater than 0 and at most 1")
    if not 0 <= args.cloud_threshold <= 100:
        parser.error("--cloud-threshold must be between 0 and 100")
    if not 1 <= args.max_fields <= MAX_FIELDS_PER_BATCH:
        parser.error(f"--max-fields must be between 1 and {MAX_FIELDS_PER_BATCH}")

    try:
        fields = load_fields(args.field_dataset, layer=args.layer)
    except ValueError as exc:
        parser.error(str(exc))

    store = RegionalRunStore(args.db)
    run_id = args.run_id or str(uuid4())
    metadata = {
        "region": args.region,
        "season": args.season,
        "dataset_name": args.dataset_name,
        "dataset_release": args.dataset_release,
        "dataset_license": args.dataset_license,
        "authorization_reference": args.authorization_reference,
        "denominator_ha": args.denominator_ha,
        "denominator_basis": args.denominator_basis,
        "denominator_source": args.denominator_source,
        "denominator_as_of": args.denominator_as_of.isoformat(),
        "start_date": args.start_date.isoformat(),
        "end_date": args.end_date.isoformat(),
        "cloud_threshold": args.cloud_threshold,
        "target_fraction": args.target_fraction,
        "non_overlapping_boundaries": True,
    }
    if args.run_id:
        saved = store.run_metadata(run_id)
        if saved is None:
            parser.error(f"No saved run exists for --run-id {run_id}")
        for key, value in metadata.items():
            if saved[key] != value:
                parser.error(f"Resume metadata differs from the saved run for {key!r}.")
        # Do not silently combine a changed manifest with a resumed run.
        incoming = {(field["field_id"], field["geometry_sha256"]) for field in fields}
        saved_fields = {
            (row["field_id"], row["geometry_sha256"]) for row in _queued_hashes(store, run_id)
        }
        if incoming != saved_fields:
            parser.error("Resume input field IDs/boundaries differ from the saved run manifest.")
    else:
        if args.end_date.isoformat() < "2017-03-28":
            parser.error("Sentinel-2 monitoring window ends before Sentinel-2 coverage begins.")
        try:
            store.create_run(run_id=run_id, metadata=metadata, fields=fields)
        except sqlite3.IntegrityError as exc:
            parser.error(f"Could not create run: {exc}")

    try:
        with _exclusive_run_lock(store, run_id):
            store.requeue_interrupted_fields(run_id)
            _execute_batch(store, run_id, fields, max_fields=args.max_fields)
    except RuntimeError as exc:
        parser.error(str(exc))
    report = store.report(run_id)
    report_path = args.report_out or REPO_ROOT / "data" / "regional-reports" / f"{run_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report["report_file"] = str(report_path.resolve())
    temporary_path = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary_path.replace(report_path)
    print(json.dumps(report, indent=2))
    return 0


def _queued_hashes(store: RegionalRunStore, run_id: str) -> list[dict[str, str]]:
    with store._connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT field_id, geometry_sha256 FROM regional_field_results WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        ]


def _execute_batch(
    store: RegionalRunStore,
    run_id: str,
    fields: Sequence[dict[str, Any]],
    *,
    max_fields: int,
    analyze: Callable[[dict[str, Any], dict[str, Any]], Any] | None = None,
) -> None:
    """Analyze a bounded serial batch and checkpoint every outcome."""
    if analyze is None:
        from app.schemas.ndvi import AnalysisOptions, NDVIAnalyzeRequest
        from app.services.analysis_service import get_analysis_service

        service = get_analysis_service()

        def analyze(field: dict[str, Any], metadata: dict[str, Any]) -> Any:
            request = NDVIAnalyzeRequest(
                aoi=field["geometry"],
                buffer_m=0,
                start_date=metadata["start_date"],
                end_date=metadata["end_date"],
                cloud_threshold=metadata["cloud_threshold"],
                options=AnalysisOptions(include_true_color_layer=False, scale_m=20),
            )
            return service.analyze(request)

    metadata = store.run_metadata(run_id)
    if metadata is None:
        raise ValueError(f"Unknown regional run ID: {run_id}")
    candidates = store.next_fields(run_id, max_fields)
    if not candidates:
        store.finish_run(run_id)
        return
    store.mark_running(run_id)
    field_by_key = {(field["field_id"], field["geometry_sha256"]): field for field in fields}
    for candidate in candidates:
        field = field_by_key.get((candidate["field_id"], candidate["geometry_sha256"]))
        if field is None:
            store.save_result(
                run_id=run_id,
                field_id=candidate["field_id"],
                geometry_sha256=candidate["geometry_sha256"],
                state="failed",
                error="Field geometry was not present in the resume input.",
            )
            continue
        try:
            result = analyze(field, metadata)
        except CropSenseError as exc:
            _record_failure(store, run_id, field, exc)
            if isinstance(exc, (EarthEngineAuthError, ConfigurationError)):
                break
            continue
        except Exception as exc:  # noqa: BLE001 - checkpoint unexpected field errors and continue
            _record_failure(store, run_id, field, exc)
            continue

        valid_fraction = result.statistics.valid_pixel_fraction
        usable_area = (
            field["cultivated_area_ha"] * valid_fraction if valid_fraction is not None else None
        )
        store.save_result(
            run_id=run_id,
            field_id=field["field_id"],
            geometry_sha256=field["geometry_sha256"],
            state="complete",
            scene_count=result.imagery.scene_count,
            mean_ndvi=result.statistics.mean,
            valid_pixel_fraction=valid_fraction,
            usable_area_ha=usable_area,
            duration_ms=result.duration_ms,
            imagery=result.imagery.model_dump(mode="json"),
            statistics=result.statistics.model_dump(mode="json"),
            health=result.health.model_dump(mode="json"),
            notes=result.notes,
            warnings=result.warnings,
        )
        print(
            f"field={field['field_id']} state=complete "
            f"area_ha={field['cultivated_area_ha']:.4f} "
            f"valid_fraction={valid_fraction if valid_fraction is not None else 'null'} "
            f"duration_ms={result.duration_ms}",
            flush=True,
        )
    store.finish_run(run_id)


def _record_failure(
    store: RegionalRunStore,
    run_id: str,
    field: dict[str, Any],
    error: Exception,
) -> None:
    """Save a field failure without swallowing its diagnostic message."""
    error_type = type(error).__name__
    error_message = str(error)[:700]
    no_imagery = isinstance(error, NoImageryError)
    store.save_result(
        run_id=run_id,
        field_id=field["field_id"],
        geometry_sha256=field["geometry_sha256"],
        state="no_imagery" if no_imagery else "failed",
        error=None if no_imagery else f"{error_type}: {error_message}",
    )
    print(
        f"field={field['field_id']} state={'no_imagery' if no_imagery else 'failed'} "
        f"error={error_type}: {error_message}",
        file=sys.stderr,
        flush=True,
    )
