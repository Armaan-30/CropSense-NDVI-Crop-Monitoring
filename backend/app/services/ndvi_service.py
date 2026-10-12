"""NDVI computation, health classification and map-layer construction.

Everything in this module is Earth Engine *expression building* plus the
visualisation metadata the dashboard needs. It never authenticates, never
queries the catalogue, and never calls ``getInfo`` - those belong to
:mod:`app.services.gee_service`.

The NDVI definition used throughout:

.. math::

    NDVI = \\frac{NIR - Red}{NIR + Red}

For Sentinel-2 Level-2A that is ``(B8 - B4) / (B8 + B4)`` at 10 m. NDVI is a
normalised ratio, so it is unaffected by the reflectance scaling applied
upstream. Values are bounded to [-1, 1]; over cropland, healthy canopy sits
roughly in 0.4-0.9, bare soil in 0.1-0.25, and water/cloud below 0.
"""

from __future__ import annotations

from typing import Any, Final

import ee

from app.core.config import Settings, get_settings
from app.core.logging_config import get_logger
from app.models.vegetation import (
    CHANGE_DISPLAY_MAX,
    CHANGE_DISPLAY_MIN,
    CHANGE_PALETTE,
    HEALTH_CLASSES,
    HEALTH_PALETTE,
    NDVI_DISPLAY_MAX,
    NDVI_DISPLAY_MIN,
    NDVI_PALETTE,
    STRESS_COLOR,
    resolve_class_bounds,
)
from app.schemas.common import LegendStop, MapLayer
from app.services.gee_service import ATTRIBUTION, GEEService

logger = get_logger(__name__)

NDVI_BAND: Final[str] = "NDVI"
HEALTH_BAND: Final[str] = "health_class"
CHANGE_BAND: Final[str] = "ndvi_change"
DECLINE_BAND: Final[str] = "decline"

# True-colour stretch. Surface reflectance over vegetated land rarely exceeds
# 0.3 in the visible bands; a 0-0.3 stretch avoids a washed-out image.
TRUE_COLOR_MIN: Final[float] = 0.0
TRUE_COLOR_MAX: Final[float] = 0.30


class NDVIService:
    """Builds NDVI imagery, health classifications and renderable layers."""

    def __init__(
        self,
        gee: GEEService,
        settings: Settings | None = None,
    ) -> None:
        self._gee = gee
        self._settings = settings or get_settings()

    # ------------------------------------------------------------------
    # Index computation
    # ------------------------------------------------------------------
    def add_ndvi_band(self, image: ee.Image) -> ee.Image:
        """Append an ``NDVI`` band to a reflectance image.

        ``normalizedDifference`` handles the division and returns values in
        [-1, 1]. Pixels masked by cloud screening stay masked.

        Args:
            image: Reflectance image containing the configured NIR and Red bands.

        Returns:
            The input image with an added ``NDVI`` band.
        """
        settings = self._settings
        ndvi = image.normalizedDifference([settings.band_nir, settings.band_red]).rename(NDVI_BAND)
        return image.addBands(ndvi)

    def add_ndvi_to_collection(self, collection: ee.ImageCollection) -> ee.ImageCollection:
        """Map :meth:`add_ndvi_band` over a whole collection."""
        return collection.map(self.add_ndvi_band)

    def ndvi_only(self, image: ee.Image) -> ee.Image:
        """Select just the NDVI band from an image."""
        return image.select([NDVI_BAND])

    # ------------------------------------------------------------------
    # Health classification
    # ------------------------------------------------------------------
    def classify_health(self, ndvi_image: ee.Image, thresholds: list[float]) -> ee.Image:
        """Bin continuous NDVI into the five integer-coded health classes.

        Class codes ascend with vigour (1 = very low ... 5 = very healthy) and
        match :data:`app.models.vegetation.HEALTH_CLASSES`. Bins are
        ``[lower, upper)`` - a pixel exactly on a threshold falls in the higher
        class.

        Cloud-masked pixels remain masked, so they are excluded from the class
        areas rather than silently counted as "very low".

        Args:
            ndvi_image: Single- or multi-band image containing ``NDVI``.
            thresholds: Exactly four ascending NDVI boundaries.

        Returns:
            A single-band ``health_class`` image (uint8).

        Raises:
            ValueError: If four ascending thresholds are not supplied.
        """
        if len(thresholds) != 4:
            raise ValueError(f"expected exactly 4 NDVI thresholds, got {len(thresholds)}")
        if list(thresholds) != sorted(thresholds):
            raise ValueError(f"NDVI thresholds must be ascending, got {thresholds}")

        ndvi = ndvi_image.select([NDVI_BAND])

        # Start everything in the lowest class, then promote upward. Each
        # `where` overwrites the previous assignment for pixels above the next
        # threshold, so the final value is the highest class the pixel qualifies for.
        classified = ee.Image.constant(HEALTH_CLASSES[0].code)
        for index, threshold in enumerate(thresholds):
            target_code = HEALTH_CLASSES[index + 1].code
            classified = classified.where(ndvi.gte(threshold), target_code)

        return classified.updateMask(ndvi.mask()).rename(HEALTH_BAND).toUint8()

    def resolve_thresholds(self, override: list[float] | None) -> tuple[list[float], str]:
        """Pick the NDVI class thresholds for a request.

        Args:
            override: Client-supplied thresholds, or None.

        Returns:
            ``(thresholds, source)`` where source is ``'request'`` or
            ``'server_default'``.

        Raises:
            ValueError: The thresholds are not four ascending values.
                Re-validated here, not only at the API boundary, because
                :meth:`classify_health` builds a cascade of ``where`` calls that
                would silently mislabel pixels if the bounds were out of order.
        """
        if override:
            thresholds = list(override)
            source = "request"
        else:
            thresholds = list(self._settings.ndvi_class_threshold_list)
            source = "server_default"

        resolve_class_bounds(thresholds)  # Raises on count/ordering problems.
        return thresholds, source

    # ------------------------------------------------------------------
    # Change detection
    # ------------------------------------------------------------------
    def ndvi_difference(self, baseline_ndvi: ee.Image, recent_ndvi: ee.Image) -> ee.Image:
        """Per-pixel NDVI change, ``recent - baseline``.

        The result is masked wherever *either* input is masked, so only pixels
        that were cloud-free in both windows are compared. That is what makes
        the change statistics honest: a pixel hidden by cloud in one period is
        excluded rather than treated as a change.

        Returns:
            A single-band ``ndvi_change`` image. Negative values mean decline.
        """
        difference = (
            recent_ndvi.select([NDVI_BAND])
            .subtract(baseline_ndvi.select([NDVI_BAND]))
            .rename(CHANGE_BAND)
        )
        both_valid = (
            baseline_ndvi.select([NDVI_BAND]).mask().And(recent_ndvi.select([NDVI_BAND]).mask())
        )
        return difference.updateMask(both_valid)

    def decline_mask(self, change_image: ee.Image, decline_threshold: float) -> ee.Image:
        """Mask of pixels whose NDVI fell by at least ``decline_threshold``.

        This is a *screening* mask for potential vegetation stress. It says
        nothing about cause - scheduled harvest, tillage, lodging, waterlogging,
        nutrient deficiency, pest pressure and normal senescence all produce
        declining NDVI.

        Args:
            change_image: Output of :meth:`ndvi_difference`.
            decline_threshold: Positive magnitude, e.g. 0.15.

        Returns:
            A self-masked single-band image that is 1 only on declining pixels.
        """
        declined = change_image.select([CHANGE_BAND]).lte(-abs(decline_threshold))
        return declined.selfMask().rename(DECLINE_BAND)

    def improvement_mask(self, change_image: ee.Image, threshold: float) -> ee.Image:
        """Mask of pixels whose NDVI rose by at least ``threshold``."""
        improved = change_image.select([CHANGE_BAND]).gte(abs(threshold))
        return improved.selfMask().rename("improvement")

    # ------------------------------------------------------------------
    # Visualisation parameters
    # ------------------------------------------------------------------
    @staticmethod
    def ndvi_vis_params() -> dict[str, Any]:
        """Visualisation parameters for the continuous NDVI layer."""
        return {
            "bands": [NDVI_BAND],
            "min": NDVI_DISPLAY_MIN,
            "max": NDVI_DISPLAY_MAX,
            "palette": list(NDVI_PALETTE),
        }

    @staticmethod
    def health_vis_params() -> dict[str, Any]:
        """Visualisation parameters for the classified health layer."""
        return {
            "bands": [HEALTH_BAND],
            "min": HEALTH_CLASSES[0].code,
            "max": HEALTH_CLASSES[-1].code,
            "palette": list(HEALTH_PALETTE),
        }

    @staticmethod
    def change_vis_params() -> dict[str, Any]:
        """Visualisation parameters for the diverging NDVI-change layer."""
        return {
            "bands": [CHANGE_BAND],
            "min": CHANGE_DISPLAY_MIN,
            "max": CHANGE_DISPLAY_MAX,
            "palette": list(CHANGE_PALETTE),
        }

    @staticmethod
    def decline_vis_params() -> dict[str, Any]:
        """Visualisation parameters for the potential-stress mask."""
        return {"bands": [DECLINE_BAND], "min": 0, "max": 1, "palette": [STRESS_COLOR]}

    def true_color_vis_params(self) -> dict[str, Any]:
        """Visualisation parameters for a natural-colour RGB layer."""
        settings = self._settings
        return {
            "bands": [settings.band_red, "B3", "B2"],
            "min": TRUE_COLOR_MIN,
            "max": TRUE_COLOR_MAX,
        }

    # ------------------------------------------------------------------
    # Legends
    # ------------------------------------------------------------------
    @staticmethod
    def ndvi_legend() -> list[LegendStop]:
        """Binned legend for the continuous NDVI palette."""
        stops: list[LegendStop] = []
        bin_count = len(NDVI_PALETTE)
        span = (NDVI_DISPLAY_MAX - NDVI_DISPLAY_MIN) / bin_count
        for index, color in enumerate(NDVI_PALETTE):
            low = NDVI_DISPLAY_MIN + index * span
            high = low + span
            stops.append(
                LegendStop(
                    label=f"{low:.2f} - {high:.2f}",
                    color=color,
                    value_min=round(low, 3),
                    value_max=round(high, 3),
                )
            )
        return stops

    @staticmethod
    def health_legend(thresholds: list[float]) -> list[LegendStop]:
        """Legend for the classified health layer, labelled with real bounds."""
        stops: list[LegendStop] = []
        for definition, lower, upper in resolve_class_bounds(thresholds):
            if lower is None:
                label = f"{definition.label} (< {upper:.2f})"
            elif upper is None:
                label = f"{definition.label} (>= {lower:.2f})"
            else:
                label = f"{definition.label} ({lower:.2f} - {upper:.2f})"
            stops.append(
                LegendStop(
                    label=label,
                    color=definition.color,
                    value_min=lower,
                    value_max=upper,
                )
            )
        return stops

    @staticmethod
    def change_legend() -> list[LegendStop]:
        """Legend for the diverging NDVI-change palette."""
        stops: list[LegendStop] = []
        bin_count = len(CHANGE_PALETTE)
        span = (CHANGE_DISPLAY_MAX - CHANGE_DISPLAY_MIN) / bin_count
        for index, color in enumerate(CHANGE_PALETTE):
            low = CHANGE_DISPLAY_MIN + index * span
            high = low + span
            stops.append(
                LegendStop(
                    label=f"{low:+.2f} - {high:+.2f}",
                    color=color,
                    value_min=round(low, 3),
                    value_max=round(high, 3),
                )
            )
        return stops

    # ------------------------------------------------------------------
    # Layer assembly
    # ------------------------------------------------------------------
    def build_ndvi_layer(self, ndvi_image: ee.Image, *, layer_id: str = "ndvi") -> MapLayer:
        """Render the NDVI image to tiles and wrap it with legend metadata."""
        url = self._gee.get_tile_url_template(ndvi_image, self.ndvi_vis_params(), label=layer_id)
        return MapLayer(
            id=layer_id,
            name="NDVI",
            description=(
                "Normalised Difference Vegetation Index from Sentinel-2 B8 (NIR) and "
                "B4 (Red) at 10 m. Higher values indicate denser, more actively "
                "photosynthesising canopy."
            ),
            tile_url_template=url,
            attribution=ATTRIBUTION,
            legend=self.ndvi_legend(),
            value_range=[NDVI_DISPLAY_MIN, NDVI_DISPLAY_MAX],
        )

    def build_health_layer(
        self,
        health_image: ee.Image,
        thresholds: list[float],
        *,
        layer_id: str = "health",
    ) -> MapLayer:
        """Render the classified health image to tiles."""
        url = self._gee.get_tile_url_template(
            health_image, self.health_vis_params(), label=layer_id
        )
        return MapLayer(
            id=layer_id,
            name="Crop health classes",
            description=(
                "NDVI binned into five vegetation-condition classes using the "
                "thresholds shown in the legend. Thresholds are configurable and "
                "require local calibration."
            ),
            tile_url_template=url,
            attribution=ATTRIBUTION,
            legend=self.health_legend(thresholds),
        )

    def build_true_color_layer(self, image: ee.Image, *, layer_id: str = "true_color") -> MapLayer:
        """Render a natural-colour RGB layer for visual cross-checking.

        Useful for spotting residual cloud, shadow or a harvested field that the
        NDVI layer alone would leave ambiguous.
        """
        url = self._gee.get_tile_url_template(image, self.true_color_vis_params(), label=layer_id)
        return MapLayer(
            id=layer_id,
            name="True colour (RGB)",
            description=(
                "Sentinel-2 natural colour composite (B4/B3/B2). Use it to sanity-check "
                "the NDVI result against what the field actually looks like."
            ),
            tile_url_template=url,
            attribution=ATTRIBUTION,
            opacity=1.0,
        )

    def build_change_layer(
        self, change_image: ee.Image, *, layer_id: str = "ndvi_change"
    ) -> MapLayer:
        """Render the per-pixel NDVI difference layer."""
        url = self._gee.get_tile_url_template(
            change_image, self.change_vis_params(), label=layer_id
        )
        return MapLayer(
            id=layer_id,
            name="NDVI change",
            description=(
                "Per-pixel NDVI difference (recent period minus baseline period). "
                "Red indicates decline, blue indicates increase. Only pixels that were "
                "cloud-free in both periods are shown."
            ),
            tile_url_template=url,
            attribution=ATTRIBUTION,
            legend=self.change_legend(),
            value_range=[CHANGE_DISPLAY_MIN, CHANGE_DISPLAY_MAX],
        )

    def build_decline_layer(
        self,
        decline_image: ee.Image,
        decline_threshold: float,
        *,
        layer_id: str = "potential_stress",
    ) -> MapLayer:
        """Render the potential-stress screening mask."""
        url = self._gee.get_tile_url_template(
            decline_image, self.decline_vis_params(), label=layer_id
        )
        return MapLayer(
            id=layer_id,
            name="Potential stress areas",
            description=(
                f"Pixels whose NDVI fell by at least {decline_threshold:.2f} between the "
                "baseline and recent periods. This flags areas for GROUND VERIFICATION. "
                "It indicates potential vegetation stress and does not identify a cause "
                "or diagnose any crop disease."
            ),
            tile_url_template=url,
            attribution=ATTRIBUTION,
            opacity=0.85,
            legend=[
                LegendStop(
                    label=f"NDVI decline >= {decline_threshold:.2f} (verify on the ground)",
                    color=STRESS_COLOR,
                )
            ],
        )
