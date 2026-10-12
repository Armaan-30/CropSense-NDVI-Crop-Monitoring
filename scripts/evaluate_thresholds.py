"""Evaluate configured NDVI class boundaries against independent field labels.

This script does not fit thresholds. Use an independently collected validation
CSV after selecting boundaries on separate calibration observations.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

CLASSES = ("very_low", "low", "moderate", "healthy", "very_healthy")
REQUIRED_COLUMNS = {"field_id", "crop_type", "growth_stage", "date", "ndvi", "observed_class"}


def predict_class(ndvi: float, thresholds: tuple[float, float, float, float]) -> str:
    """Map a numeric NDVI into the project's ordered five-class convention."""
    for threshold, label in zip(thresholds, CLASSES, strict=False):
        if ndvi < threshold:
            return label
    return CLASSES[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Independent ground-observation CSV")
    parser.add_argument(
        "--thresholds",
        required=True,
        help="Four ascending boundaries, e.g. 0.18,0.36,0.58,0.76",
    )
    parser.add_argument(
        "--independent-validation",
        action="store_true",
        help="Confirm this file was held out from threshold selection",
    )
    args = parser.parse_args()

    try:
        thresholds = tuple(float(value.strip()) for value in args.thresholds.split(","))
    except ValueError:
        parser.error("--thresholds must contain four numeric comma-separated values")
    if len(thresholds) != 4 or any(not -1 <= value <= 1 for value in thresholds):
        parser.error("--thresholds must contain exactly four values in [-1, 1]")
    if tuple(sorted(set(thresholds))) != thresholds:
        parser.error("--thresholds must be strictly ascending")
    if not args.independent_validation:
        parser.error(
            "refusing to report accuracy without --independent-validation; "
            "use observations not used to choose these thresholds"
        )

    with args.csv_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            parser.error(f"CSV is missing required columns: {', '.join(sorted(missing))}")
        rows: list[tuple[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            actual = (row.get("observed_class") or "").strip().lower()
            try:
                ndvi = float(row.get("ndvi") or "")
            except ValueError:
                parser.error(f"row {line_number}: ndvi must be numeric")
            if actual not in CLASSES:
                labels = ", ".join(CLASSES)
                parser.error(f"row {line_number}: observed_class must be one of {labels}")
            if not -1 <= ndvi <= 1:
                parser.error(f"row {line_number}: NDVI must be in [-1, 1]")
            rows.append((actual, predict_class(ndvi, thresholds)))

    if not rows:
        parser.error("CSV contains no observations")

    matrix = {actual: Counter() for actual in CLASSES}
    for actual, predicted in rows:
        matrix[actual][predicted] += 1
    f1_values: list[float] = []
    for label in CLASSES:
        true_positive = matrix[label][label]
        actual_count = sum(matrix[label].values())
        predicted_count = sum(matrix[actual][label] for actual in CLASSES)
        recall = true_positive / actual_count if actual_count else 0.0
        precision = true_positive / predicted_count if predicted_count else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        if actual_count:
            f1_values.append(f1)
        print(
            f"{label}: n={actual_count}, precision={precision:.3f}, "
            f"recall={recall:.3f}, f1={f1:.3f}"
        )

    correct = sum(matrix[label][label] for label in CLASSES)
    print(f"observations={len(rows)}")
    print(f"thresholds={','.join(f'{value:g}' for value in thresholds)}")
    print(f"accuracy={correct / len(rows):.3f}")
    print(f"macro_f1={sum(f1_values) / len(f1_values):.3f}")
    print("confusion_matrix_rows=observed,columns=predicted")
    print("observed," + ",".join(CLASSES))
    for actual in CLASSES:
        print(actual + "," + ",".join(str(matrix[actual][predicted]) for predicted in CLASSES))
    print(
        "Validation metrics describe this supplied holdout only; they are not universal accuracy."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
