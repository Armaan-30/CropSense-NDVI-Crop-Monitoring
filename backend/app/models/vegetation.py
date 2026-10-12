"""Vegetation-condition domain model: classes, palettes and interpretation text.

This module holds the *definitions* of the five NDVI health classes. The
numeric boundaries are supplied at call time from configuration or the request,
never hard-coded here, because they are the part that must be calibrated.

Scientific position taken by CropSense
--------------------------------------
NDVI is a normalised ratio of near-infrared to red reflectance. It responds to
green canopy density, leaf area and chlorophyll activity, so it is a reasonable
proxy for *vegetation vigour*. It does not identify a cause. A low or falling
NDVI is consistent with water stress, nutrient deficiency, pest or disease
pressure, waterlogging, lodging, harvest, or simply a crop that has reached
senescence on schedule. Distinguishing between those requires ground
observation, agronomic context, and usually additional data.

Accordingly, every user-facing string in this module says "potential" or
"possible" and none of them names a disease.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# ---------------------------------------------------------------------------
# Health classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthClassDefinition:
    """Static definition of one vegetation-condition class.

    Attributes:
        key: Stable machine identifier used in API payloads.
        label: Display label for the dashboard.
        color: CSS hex colour, shared by the map layer, legend and charts.
        code: Integer code used for the classified raster (ascending with vigour).
        description: What this class typically corresponds to on the ground.
    """

    key: str
    label: str
    color: str
    code: int
    description: str


# Ordered from least to most vegetation vigour. The palette is a
# brown -> yellow -> green progression that stays distinguishable in
# grayscale and for the most common forms of colour-vision deficiency.
HEALTH_CLASSES: Final[tuple[HealthClassDefinition, ...]] = (
    HealthClassDefinition(
        key="very_low",
        label="Very Low / Non-vegetated",
        color="#a6611a",
        code=1,
        description=(
            "Little or no photosynthetically active vegetation. Typically bare soil, "
            "a recently tilled or harvested field, water, built-up surface, or fully "
            "senesced crop residue."
        ),
    ),
    HealthClassDefinition(
        key="low",
        label="Low",
        color="#dfc27d",
        code=2,
        description=(
            "Sparse or weak canopy. Consistent with early emergence, poor "
            "establishment, or vegetation under substantial stress. Cause cannot be "
            "determined from NDVI alone."
        ),
    ),
    HealthClassDefinition(
        key="moderate",
        label="Moderate",
        color="#f5f5c1",
        code=3,
        description=(
            "Partial canopy cover or moderate vigour. Common mid-development, and "
            "also seen where growth is being limited by water or nutrients."
        ),
    ),
    HealthClassDefinition(
        key="healthy",
        label="Healthy",
        color="#80cdc1",
        code=4,
        description=(
            "Dense, actively photosynthesising canopy consistent with a well-developed "
            "crop for many species and growth stages."
        ),
    ),
    HealthClassDefinition(
        key="very_healthy",
        label="Very Healthy",
        color="#018571",
        code=5,
        description=(
            "Very dense canopy near the sensor's saturation range. NDVI loses "
            "sensitivity here, so differences within this class are not reliable."
        ),
    ),
)

HEALTH_CLASS_BY_KEY: Final[dict[str, HealthClassDefinition]] = {
    definition.key: definition for definition in HEALTH_CLASSES
}

HEALTH_PALETTE: Final[tuple[str, ...]] = tuple(definition.color for definition in HEALTH_CLASSES)

# ---------------------------------------------------------------------------
# Continuous NDVI palette
# ---------------------------------------------------------------------------

# Brown -> tan -> pale -> teal -> dark green. Perceptually ordered and
# colour-vision-deficiency friendly (derived from the ColorBrewer BrBG scheme).
NDVI_PALETTE: Final[tuple[str, ...]] = (
    "#8c510a",
    "#bf812d",
    "#dfc27d",
    "#f6e8c3",
    "#f5f5f5",
    "#c7eae5",
    "#80cdc1",
    "#35978f",
    "#01665e",
    "#003c30",
)

# NDVI over agricultural land almost never falls below 0 (that indicates water,
# snow or cloud) and rarely exceeds 0.95. Stretching 0 -> 0.9 uses the full
# palette on the range that actually carries agronomic signal.
NDVI_DISPLAY_MIN: Final[float] = 0.0
NDVI_DISPLAY_MAX: Final[float] = 0.9

# Diverging red -> white -> green for NDVI change maps.
CHANGE_PALETTE: Final[tuple[str, ...]] = (
    "#67001f",
    "#b2182b",
    "#d6604d",
    "#f4a582",
    "#fddbc7",
    "#f7f7f7",
    "#d1e5f0",
    "#92c5de",
    "#4393c3",
    "#2166ac",
    "#053061",
)
CHANGE_DISPLAY_MIN: Final[float] = -0.4
CHANGE_DISPLAY_MAX: Final[float] = 0.4

STRESS_COLOR: Final[str] = "#d7191c"

# ---------------------------------------------------------------------------
# Standing caveats surfaced through the API
# ---------------------------------------------------------------------------

CALIBRATION_NOTE: Final[str] = (
    "NDVI class boundaries are configurable and the defaults are generic starting "
    "points only. Absolute NDVI values that indicate a healthy crop vary with crop "
    "type, growth stage, canopy architecture, soil background, region, season and "
    "atmospheric conditions. Calibrate these thresholds against ground observations "
    "for your own fields before using them operationally."
)

STRESS_NOTE: Final[str] = (
    "Areas flagged here show a statistically notable NDVI decline relative to the "
    "baseline period. That indicates POTENTIAL vegetation stress requiring ground "
    "verification. NDVI cannot identify the cause and cannot diagnose a specific "
    "crop disease. Scheduled harvest, tillage, irrigation changes, lodging, "
    "waterlogging, nutrient deficiency, pest pressure and normal senescence can all "
    "produce the same signal."
)

GENERAL_LIMITATIONS: Final[tuple[str, ...]] = (
    "NDVI measures vegetation vigour, not crop health causes. It cannot diagnose a "
    "specific disease, pest or pathogen.",
    "Sentinel-2 revisit is 2-5 days at the equator with two satellites, but usable "
    "observations are far sparser during cloudy seasons. Gaps in the time series are "
    "expected, not errors.",
    "Cloud and cloud-shadow masking is imperfect. Residual thin cirrus or unmasked "
    "shadow depresses NDVI and can look like stress.",
    "NDVI saturates over dense canopies (roughly above 0.8), so it under-reports "
    "differences in vigorous, closed-canopy crops.",
    "Sentinel-2 B4/B8 are 10 m bands. Field-edge pixels mix crop with roads, bunds "
    "and neighbouring fields; small or narrow fields are disproportionately affected.",
    "Surface reflectance (L2A) is atmospherically corrected by Sen2Cor, which has "
    "known residual errors over bright soils and in hazy conditions.",
    "Statistics are computed only over cloud-free pixels. Always read them together "
    "with the reported valid-pixel fraction.",
    "CropSense reports no accuracy or validation metrics because none have been "
    "established for this deployment. Any such figures would have to come from your "
    "own field validation campaign.",
)


def resolve_class_bounds(
    thresholds: list[float],
) -> list[tuple[HealthClassDefinition, float | None, float | None]]:
    """Pair each health class with its numeric NDVI bounds.

    Args:
        thresholds: Exactly four ascending NDVI boundaries.

    Returns:
        A list of ``(definition, lower_bound, upper_bound)`` tuples in ascending
        vigour order. ``lower_bound`` is inclusive, ``upper_bound`` exclusive.
        ``None`` means "open" (i.e. -1 for the first class, +1 for the last).

    Raises:
        ValueError: If four ascending thresholds are not supplied.
    """
    if len(thresholds) != 4:
        raise ValueError(f"expected exactly 4 thresholds, got {len(thresholds)}")
    if list(thresholds) != sorted(thresholds):
        raise ValueError(f"thresholds must be ascending, got {thresholds}")

    bounds: list[float | None] = [None, *thresholds, None]
    return [
        (definition, bounds[index], bounds[index + 1])
        for index, definition in enumerate(HEALTH_CLASSES)
    ]
