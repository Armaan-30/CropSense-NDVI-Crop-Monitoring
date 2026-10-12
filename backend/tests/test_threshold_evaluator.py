"""Safety and behavior checks for the independent-validation evaluator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATOR = REPO_ROOT / "scripts" / "evaluate_thresholds.py"


def test_evaluator_refuses_metrics_without_explicit_holdout_confirmation(tmp_path: Path) -> None:
    observations = tmp_path / "observations.csv"
    observations.write_text(
        "field_id,crop_type,growth_stage,date,ndvi,observed_class\n"
        "f1,cotton,flowering,2026-09-01,0.3,low\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(EVALUATOR), str(observations), "--thresholds", "0.2,0.4,0.6,0.8"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "refusing to report accuracy" in result.stderr


def test_evaluator_reports_metrics_for_supplied_holdout_only(tmp_path: Path) -> None:
    observations = tmp_path / "synthetic-holdout.csv"
    observations.write_text(
        "field_id,crop_type,growth_stage,date,ndvi,observed_class\n"
        "f1,cotton,stage,2026-09-01,0.1,very_low\n"
        "f2,cotton,stage,2026-09-01,0.3,low\n"
        "f3,cotton,stage,2026-09-01,0.5,moderate\n"
        "f4,cotton,stage,2026-09-01,0.7,healthy\n"
        "f5,cotton,stage,2026-09-01,0.9,very_healthy\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(EVALUATOR),
            str(observations),
            "--thresholds",
            "0.2,0.4,0.6,0.8",
            "--independent-validation",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "observations=5" in result.stdout
    assert "accuracy=1.000" in result.stdout
    assert "Validation metrics describe this supplied holdout only" in result.stdout
