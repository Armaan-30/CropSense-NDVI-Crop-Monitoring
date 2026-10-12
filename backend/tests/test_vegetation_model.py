"""Tests for the vegetation domain model."""

from __future__ import annotations

import re

import pytest

from app.models.vegetation import (
    CALIBRATION_NOTE,
    GENERAL_LIMITATIONS,
    HEALTH_CLASSES,
    HEALTH_PALETTE,
    NDVI_PALETTE,
    STRESS_NOTE,
    resolve_class_bounds,
)

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_five_classes_with_ascending_codes() -> None:
    assert len(HEALTH_CLASSES) == 5
    assert [definition.code for definition in HEALTH_CLASSES] == [1, 2, 3, 4, 5]


def test_class_keys_are_unique() -> None:
    keys = [definition.key for definition in HEALTH_CLASSES]
    assert len(set(keys)) == len(keys)


def test_all_palette_colors_are_valid_hex() -> None:
    for color in (*HEALTH_PALETTE, *NDVI_PALETTE):
        assert HEX_COLOR.match(color), color


def test_health_palette_length_matches_class_count() -> None:
    assert len(HEALTH_PALETTE) == len(HEALTH_CLASSES)


def test_resolve_class_bounds_produces_contiguous_bins() -> None:
    bounds = resolve_class_bounds([0.2, 0.4, 0.6, 0.8])
    assert len(bounds) == 5
    assert bounds[0][1] is None and bounds[0][2] == 0.2
    assert bounds[4][1] == 0.8 and bounds[4][2] is None
    # Each bin's upper bound is the next bin's lower bound - no gaps, no overlaps.
    for index in range(len(bounds) - 1):
        assert bounds[index][2] == bounds[index + 1][1]


def test_resolve_class_bounds_rejects_wrong_count() -> None:
    with pytest.raises(ValueError, match="exactly 4"):
        resolve_class_bounds([0.2, 0.4, 0.6])


def test_resolve_class_bounds_rejects_descending() -> None:
    with pytest.raises(ValueError, match="ascending"):
        resolve_class_bounds([0.8, 0.6, 0.4, 0.2])


def test_calibration_note_warns_against_universal_thresholds() -> None:
    lowered = CALIBRATION_NOTE.lower()
    assert "generic" in lowered
    assert "calibrate" in lowered
    assert "crop type" in lowered
    assert "growth stage" in lowered


def test_stress_note_says_potential_and_refuses_diagnosis() -> None:
    lowered = STRESS_NOTE.lower()
    assert "potential" in lowered
    assert "cannot identify the cause" in lowered
    assert "cannot diagnose" in lowered


def test_limitations_disclaim_fabricated_accuracy_metrics() -> None:
    joined = " ".join(GENERAL_LIMITATIONS).lower()
    assert "no accuracy or validation metrics" in joined
    assert "saturates" in joined
    assert "cannot diagnose" in joined


def test_no_class_description_names_a_disease() -> None:
    """Guard against a future edit smuggling a diagnostic claim into the model."""
    forbidden = ("blight", "rust", "mildew", "disease diagnosis", "infection")
    for definition in HEALTH_CLASSES:
        lowered = definition.description.lower()
        for term in forbidden:
            assert term not in lowered, f"{definition.key} description mentions {term}"
