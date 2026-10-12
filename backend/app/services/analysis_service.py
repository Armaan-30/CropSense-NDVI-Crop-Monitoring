"""Analysis orchestration: turns API requests into complete, caveated results.

This module sequences the work - resolve options, measure the AOI, filter the
Sentinel-2 collection, composite, compute NDVI, classify, reduce statistics,
render tiles - and assembles the response. The numeric post-processing it needs
lives in :mod:`app.services.metrics` (pure Python), and every Earth Engine
client concern lives in :mod:`app.services.gee_service`.

Round-trip discipline
---------------------
Earth Engine calls are the dominant cost, so statistics are batched into a
single ``ee.Dictionary`` per analysis and evaluated once. A full NDVI analysis
costs roughly: 1 AOI measurement + 1 collection metadata + 1 batched statistics
evaluation + 1 tile registration per requested layer.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any, Final

import ee

from app.core.config import Settings, get_settings
from app.core.exceptions import InvalidRequestError
from app.core.logging_config import get_logger
from app.models.vegetation import (
    GENERAL_LIMITATIONS,
    STRESS_NOTE,
)
from app.schemas.common import (
    CloudMaskMethod,
    CompositeMethod,
    DateRange,
    ImagerySummary,
    MapLayer,
    TemporalAggregation,
)
from app.schemas.ndvi import (
    AnalysisOptions,
    ChangeDetectionRequest,
    ChangeDetectionResponse,
    ChangeStatistics,
    NDVIAnalyzeRequest,
    NDVIAnalyzeResponse,
    TimeSeriesPoint,
    TimeSeriesRequest,
    TimeSeriesResponse,
)
from app.services import metrics
from app.services.gee_service import (
    CLOUD_SCORE_PLUS_START,
    SENTINEL2_START,
    GEEService,
    get_gee_service,
)
from app.services.ndvi_service import (
    CHANGE_BAND,
    HEALTH_BAND,
    NDVI_BAND,
    NDVIService,
)

logger = get_logger(__name__)

# Time-step of each calendar aggregation bin, in days.
_AGGREGATION_DAYS: Final[dict[TemporalAggregation, int]] = {
    TemporalAggregation.WEEKLY: 7,
    TemporalAggregation.BIWEEKLY: 14,
    TemporalAggregation.MONTHLY: 30,
}


class AnalysisService:
    """High-level NDVI analyses over an AOI."""

    def __init__(
        self,
        gee: GEEService | None = None,
        ndvi: NDVIService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._gee = gee or get_gee_service()
        self._ndvi = ndvi or NDVIService(self._gee, self._settings)

    # ==================================================================
    # Public API
    # ==================================================================
    def analyze(self, request: NDVIAnalyzeRequest) -> NDVIAnalyzeResponse:
        """Run a full single-window NDVI analysis.

        Args:
            request: Validated analysis request.

        Returns:
            Statistics, health classification, map layers and caveats.

        Raises:
            InvalidRequestError: The date window violates a configured limit.
            InvalidAOIError: The AOI is unusable or too large.
            NoImageryError: No scenes matched the filters.
            EarthEngineError / EarthEngineAuthError: Earth Engine problems.
        """
        started = time.perf_counter()
        date_range = request.date_range
        warnings: list[str] = []

        self._validate_window(date_range, warnings)
        options = request.options
        mask_method = self._resolve_mask_method(options, date_range, warnings)
        composite_method = options.composite_method or CompositeMethod.MEDIAN
        scale = self._gee.resolve_scale(options.scale_m)
        thresholds, thresholds_source = self._ndvi.resolve_thresholds(options.ndvi_class_thresholds)
        self._warn_on_composite_choice(composite_method, warnings)

        geometry = self._gee.build_geometry(request.aoi, buffer_m=request.buffer_m)
        aoi_summary = self._gee.summarize_aoi(geometry, geometry_type=request.aoi["type"])
        aoi_area_m2 = aoi_summary.area_ha * metrics.M2_PER_HECTARE

        collection = self._gee.build_sentinel2_collection(
            geometry,
            date_range,
            request.cloud_threshold,
            cloud_mask_method=mask_method,
            cloud_score_plus_threshold=options.cloud_score_plus_threshold,
        )
        collection = self._ndvi.add_ndvi_to_collection(collection)

        scene_info = self._gee.collection_metadata(collection, label="scene metadata")
        self._gee.require_non_empty(
            scene_info["count"],
            date_range=date_range,
            cloud_threshold=request.cloud_threshold,
            collection_id=self._settings.s2_collection_id,
        )

        composite = self._gee.clip(
            self._gee.composite(collection, composite_method, quality_band=NDVI_BAND),
            geometry,
        )
        ndvi_image = self._ndvi.ndvi_only(composite)
        health_image = self._ndvi.classify_health(ndvi_image, thresholds)

        batched = ee.Dictionary(
            {
                "stats": self._gee.reduce_statistics(
                    ndvi_image, geometry, band=NDVI_BAND, scale=scale
                ),
                "valid_area_m2": self._gee.reduce_valid_area_m2(
                    ndvi_image, geometry, band=NDVI_BAND, scale=scale
                ),
                "class_areas": self._gee.reduce_area_by_class(
                    health_image, geometry, class_band=HEALTH_BAND, scale=scale
                ),
            }
        )
        evaluated = self._gee.evaluate(batched, label="NDVI statistics")

        statistics = metrics.parse_zonal_statistics(
            evaluated.get("stats"),
            band=NDVI_BAND,
            scale_m=scale,
            valid_area_m2=evaluated.get("valid_area_m2"),
            aoi_area_m2=aoi_area_m2,
        )
        health = metrics.build_health_summary(
            evaluated.get("class_areas"),
            thresholds=thresholds,
            thresholds_source=thresholds_source,
        )

        layers = self._build_analysis_layers(
            ndvi_image=ndvi_image,
            health_image=health_image,
            composite=composite,
            thresholds=thresholds,
            include_true_color=options.include_true_color_layer,
        )

        warnings.extend(
            metrics.build_quality_warnings(
                scene_count=scene_info["count"],
                statistics=statistics,
                cloud_threshold=request.cloud_threshold,
                window_days=date_range.days,
            )
        )

        notes = list(GENERAL_LIMITATIONS)
        coverage_note = metrics.build_class_area_note(health, aoi_summary.area_ha)
        if coverage_note:
            notes.insert(0, coverage_note)

        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "NDVI analysis complete: %d scenes, mean=%s, %d ms",
            scene_info["count"],
            statistics.mean,
            duration_ms,
        )

        return NDVIAnalyzeResponse(
            aoi=aoi_summary,
            imagery=self._build_imagery_summary(
                scene_info,
                date_range=date_range,
                cloud_threshold=request.cloud_threshold,
                mask_method=mask_method,
                composite_method=composite_method,
            ),
            statistics=statistics,
            health=health,
            layers=layers,
            warnings=warnings,
            notes=notes,
            computed_at=metrics.utc_now_iso(),
            duration_ms=duration_ms,
        )

    def time_series(self, request: TimeSeriesRequest) -> TimeSeriesResponse:
        """Build an NDVI time series and fit a linear trend to it.

        With ``aggregation='scene'`` one point is produced per usable overpass.
        With a calendar aggregation, scenes inside each bin are composited
        per-pixel first, which fills small cloud gaps at the cost of temporal
        precision.

        Raises:
            InvalidRequestError: The window violates a configured limit.
            NoImageryError: No scenes matched the filters.
        """
        started = time.perf_counter()
        date_range = DateRange(start_date=request.start_date, end_date=request.end_date)
        warnings: list[str] = []

        self._validate_window(date_range, warnings)
        options = request.options
        mask_method = self._resolve_mask_method(options, date_range, warnings)
        scale = self._gee.resolve_scale(options.scale_m)

        geometry = self._gee.build_geometry(request.aoi, buffer_m=request.buffer_m)
        aoi_summary = self._gee.summarize_aoi(geometry, geometry_type=request.aoi["type"])
        aoi_area_m2 = aoi_summary.area_ha * metrics.M2_PER_HECTARE

        collection = self._gee.build_sentinel2_collection(
            geometry,
            date_range,
            request.cloud_threshold,
            cloud_mask_method=mask_method,
            cloud_score_plus_threshold=options.cloud_score_plus_threshold,
        )
        collection = self._ndvi.add_ndvi_to_collection(collection)

        scene_info = self._gee.collection_metadata(collection, label="time-series metadata")
        self._gee.require_non_empty(
            scene_info["count"],
            date_range=date_range,
            cloud_threshold=request.cloud_threshold,
            collection_id=self._settings.s2_collection_id,
        )

        if request.aggregation is TemporalAggregation.SCENE:
            raw_points = self._per_scene_series(
                collection,
                geometry,
                scale=scale,
                scene_count=scene_info["count"],
                aoi_area_m2=aoi_area_m2,
                warnings=warnings,
            )
        else:
            raw_points = self._binned_series(
                collection,
                geometry,
                date_range=date_range,
                aggregation=request.aggregation,
                scale=scale,
                aoi_area_m2=aoi_area_m2,
                composite_method=options.composite_method or CompositeMethod.MEDIAN,
                warnings=warnings,
            )

        kept: list[TimeSeriesPoint] = []
        excluded = 0
        for point in raw_points:
            if point.mean_ndvi is None:
                excluded += 1
                continue
            fraction = point.valid_pixel_fraction
            if fraction is not None and fraction < request.min_valid_fraction:
                excluded += 1
                continue
            kept.append(point)

        kept.sort(key=lambda item: item.date)

        if excluded:
            warnings.append(
                f"{excluded} observation(s) were dropped for having no cloud-free pixels "
                f"or covering less than {request.min_valid_fraction * 100:.0f}% of the AOI. "
                "Lower min_valid_fraction to include them, at the cost of reliability."
            )
        if not kept:
            warnings.append(
                "Every observation in this window fell below the minimum cloud-free "
                "coverage. No trend could be computed."
            )

        gap_warning = self._largest_gap_warning(kept)
        if gap_warning:
            warnings.append(gap_warning)

        trend = metrics.fit_linear_trend(kept)
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "Time series complete: %d points kept, %d excluded, direction=%s, %d ms",
            len(kept),
            excluded,
            trend.direction,
            duration_ms,
        )

        return TimeSeriesResponse(
            aoi=aoi_summary,
            collection_id=self._settings.s2_collection_id,
            requested_range=date_range,
            aggregation=request.aggregation,
            cloud_threshold_percent=request.cloud_threshold,
            cloud_mask_method=mask_method,
            scale_m=scale,
            points=kept,
            excluded_point_count=excluded,
            trend=trend,
            warnings=warnings,
            notes=list(GENERAL_LIMITATIONS),
            computed_at=metrics.utc_now_iso(),
            duration_ms=duration_ms,
        )

    def detect_change(self, request: ChangeDetectionRequest) -> ChangeDetectionResponse:
        """Compare two periods and screen for areas of significant NDVI decline.

        Both windows are composited independently and differenced per pixel.
        Only pixels that were cloud-free in *both* windows are compared, so the
        change statistics are not contaminated by cloud gaps.

        Raises:
            InvalidRequestError: A window violates a configured limit.
            NoImageryError: Either window had no usable scenes.
        """
        started = time.perf_counter()
        baseline_range = request.baseline_range
        recent_range = request.recent_range
        warnings: list[str] = []

        self._validate_window(baseline_range, warnings, label="baseline window")
        self._validate_window(recent_range, warnings, label="recent window")

        options = request.options
        mask_method = self._resolve_mask_method(options, baseline_range, warnings)
        composite_method = options.composite_method or CompositeMethod.MEDIAN
        scale = self._gee.resolve_scale(options.scale_m)
        thresholds, thresholds_source = self._ndvi.resolve_thresholds(options.ndvi_class_thresholds)
        decline_threshold = (
            request.decline_threshold
            if request.decline_threshold is not None
            else self._settings.ndvi_decline_threshold
        )

        if _windows_overlap(baseline_range, recent_range):
            warnings.append(
                "The baseline and recent windows overlap, so they share scenes. The "
                "measured change will be damped toward zero."
            )

        geometry = self._gee.build_geometry(request.aoi, buffer_m=request.buffer_m)
        aoi_summary = self._gee.summarize_aoi(geometry, geometry_type=request.aoi["type"])
        aoi_area_m2 = aoi_summary.area_ha * metrics.M2_PER_HECTARE

        baseline_collection, baseline_info = self._prepare_window(
            geometry, baseline_range, request.cloud_threshold, mask_method, options, "baseline"
        )
        recent_collection, recent_info = self._prepare_window(
            geometry, recent_range, request.cloud_threshold, mask_method, options, "recent"
        )

        baseline_composite = self._gee.clip(
            self._gee.composite(baseline_collection, composite_method, quality_band=NDVI_BAND),
            geometry,
        )
        recent_composite = self._gee.clip(
            self._gee.composite(recent_collection, composite_method, quality_band=NDVI_BAND),
            geometry,
        )

        baseline_ndvi = self._ndvi.ndvi_only(baseline_composite)
        recent_ndvi = self._ndvi.ndvi_only(recent_composite)
        baseline_health = self._ndvi.classify_health(baseline_ndvi, thresholds)
        recent_health = self._ndvi.classify_health(recent_ndvi, thresholds)

        change_image = self._ndvi.ndvi_difference(baseline_ndvi, recent_ndvi)
        decline_image = self._ndvi.decline_mask(change_image, decline_threshold)
        improvement_image = self._ndvi.improvement_mask(change_image, decline_threshold)

        batched = ee.Dictionary(
            {
                "baseline_stats": self._gee.reduce_statistics(
                    baseline_ndvi, geometry, band=NDVI_BAND, scale=scale
                ),
                "baseline_valid_area_m2": self._gee.reduce_valid_area_m2(
                    baseline_ndvi, geometry, band=NDVI_BAND, scale=scale
                ),
                "baseline_class_areas": self._gee.reduce_area_by_class(
                    baseline_health, geometry, class_band=HEALTH_BAND, scale=scale
                ),
                "recent_stats": self._gee.reduce_statistics(
                    recent_ndvi, geometry, band=NDVI_BAND, scale=scale
                ),
                "recent_valid_area_m2": self._gee.reduce_valid_area_m2(
                    recent_ndvi, geometry, band=NDVI_BAND, scale=scale
                ),
                "recent_class_areas": self._gee.reduce_area_by_class(
                    recent_health, geometry, class_band=HEALTH_BAND, scale=scale
                ),
                "change_stats": self._gee.reduce_statistics(
                    change_image, geometry, band=CHANGE_BAND, scale=scale
                ),
                "comparable_area_m2": self._gee.reduce_valid_area_m2(
                    change_image, geometry, band=CHANGE_BAND, scale=scale
                ),
                "declined_area_m2": self._gee.reduce_masked_area_m2(
                    decline_image, geometry, scale=scale
                ),
                "improved_area_m2": self._gee.reduce_masked_area_m2(
                    improvement_image, geometry, scale=scale
                ),
            }
        )
        evaluated = self._gee.evaluate(batched, label="change-detection statistics")

        baseline_statistics = metrics.parse_zonal_statistics(
            evaluated.get("baseline_stats"),
            band=NDVI_BAND,
            scale_m=scale,
            valid_area_m2=evaluated.get("baseline_valid_area_m2"),
            aoi_area_m2=aoi_area_m2,
        )
        recent_statistics = metrics.parse_zonal_statistics(
            evaluated.get("recent_stats"),
            band=NDVI_BAND,
            scale_m=scale,
            valid_area_m2=evaluated.get("recent_valid_area_m2"),
            aoi_area_m2=aoi_area_m2,
        )
        change_raw = metrics.parse_zonal_statistics(
            evaluated.get("change_stats"),
            band=CHANGE_BAND,
            scale_m=scale,
            valid_area_m2=evaluated.get("comparable_area_m2"),
            aoi_area_m2=aoi_area_m2,
        )

        comparable_m2 = float(evaluated.get("comparable_area_m2") or 0.0)
        declined_m2 = float(evaluated.get("declined_area_m2") or 0.0)
        improved_m2 = float(evaluated.get("improved_area_m2") or 0.0)

        change_statistics = ChangeStatistics(
            mean_change=change_raw.mean,
            min_change=change_raw.min,
            max_change=change_raw.max,
            median_change=change_raw.median,
            std_dev_change=change_raw.std_dev,
            comparable_area_ha=metrics.m2_to_ha(comparable_m2),
            comparable_area_fraction=(
                round(min(comparable_m2 / aoi_area_m2, 1.0), 4) if aoi_area_m2 > 0 else None
            ),
            declined_area_ha=metrics.m2_to_ha(declined_m2),
            declined_percent_of_comparable=metrics.safe_percent(declined_m2, comparable_m2),
            improved_area_ha=metrics.m2_to_ha(improved_m2),
            improved_percent_of_comparable=metrics.safe_percent(improved_m2, comparable_m2),
            decline_threshold=decline_threshold,
        )

        layers = [
            self._ndvi.build_ndvi_layer(baseline_ndvi, layer_id="ndvi_baseline"),
            self._ndvi.build_ndvi_layer(recent_ndvi, layer_id="ndvi_recent"),
            self._ndvi.build_change_layer(change_image),
            self._ndvi.build_decline_layer(decline_image, decline_threshold),
        ]
        # Distinguish the two NDVI layers in the UI's layer switcher.
        layers[
            0
        ].name = f"NDVI - baseline ({baseline_range.start_date} to {baseline_range.end_date})"
        layers[1].name = f"NDVI - recent ({recent_range.start_date} to {recent_range.end_date})"

        warnings.extend(
            self._change_warnings(
                comparable_m2=comparable_m2,
                aoi_area_m2=aoi_area_m2,
                baseline_scenes=baseline_info["count"],
                recent_scenes=recent_info["count"],
            )
        )

        notes = [STRESS_NOTE, *GENERAL_LIMITATIONS]
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "Change detection complete: %.2f ha declined of %.2f ha comparable, %d ms",
            change_statistics.declined_area_ha,
            change_statistics.comparable_area_ha,
            duration_ms,
        )

        return ChangeDetectionResponse(
            aoi=aoi_summary,
            baseline_imagery=self._build_imagery_summary(
                baseline_info,
                date_range=baseline_range,
                cloud_threshold=request.cloud_threshold,
                mask_method=mask_method,
                composite_method=composite_method,
            ),
            recent_imagery=self._build_imagery_summary(
                recent_info,
                date_range=recent_range,
                cloud_threshold=request.cloud_threshold,
                mask_method=mask_method,
                composite_method=composite_method,
            ),
            baseline_statistics=baseline_statistics,
            recent_statistics=recent_statistics,
            baseline_health=metrics.build_health_summary(
                evaluated.get("baseline_class_areas"),
                thresholds=thresholds,
                thresholds_source=thresholds_source,
            ),
            recent_health=metrics.build_health_summary(
                evaluated.get("recent_class_areas"),
                thresholds=thresholds,
                thresholds_source=thresholds_source,
            ),
            change=change_statistics,
            layers=layers,
            warnings=warnings,
            notes=notes,
            computed_at=metrics.utc_now_iso(),
            duration_ms=duration_ms,
        )

    # ==================================================================
    # Internals
    # ==================================================================
    def _prepare_window(
        self,
        geometry: ee.Geometry,
        date_range: DateRange,
        cloud_threshold: float,
        mask_method: CloudMaskMethod,
        options: AnalysisOptions,
        label: str,
    ) -> tuple[ee.ImageCollection, dict[str, Any]]:
        """Filter, mask and describe one date window; fail if it is empty."""
        collection = self._gee.build_sentinel2_collection(
            geometry,
            date_range,
            cloud_threshold,
            cloud_mask_method=mask_method,
            cloud_score_plus_threshold=options.cloud_score_plus_threshold,
        )
        collection = self._ndvi.add_ndvi_to_collection(collection)
        info = self._gee.collection_metadata(collection, label=f"{label} metadata")
        self._gee.require_non_empty(
            info["count"],
            date_range=date_range,
            cloud_threshold=cloud_threshold,
            collection_id=self._settings.s2_collection_id,
        )
        return collection, info

    def _build_analysis_layers(
        self,
        *,
        ndvi_image: ee.Image,
        health_image: ee.Image,
        composite: ee.Image,
        thresholds: list[float],
        include_true_color: bool,
    ) -> list[MapLayer]:
        """Register tile endpoints for the layers the dashboard will display."""
        layers = [
            self._ndvi.build_ndvi_layer(ndvi_image),
            self._ndvi.build_health_layer(health_image, thresholds),
        ]
        if include_true_color:
            layers.append(self._ndvi.build_true_color_layer(composite))
        return layers

    def _build_imagery_summary(
        self,
        scene_info: dict[str, Any],
        *,
        date_range: DateRange,
        cloud_threshold: float,
        mask_method: CloudMaskMethod,
        composite_method: CompositeMethod,
    ) -> ImagerySummary:
        """Assemble the provenance block from raw collection metadata."""
        timestamps = scene_info.get("timestamps_ms") or []
        dates = [
            value for value in (metrics.epoch_ms_to_date_str(ts) for ts in timestamps) if value
        ]
        return ImagerySummary(
            collection_id=self._settings.s2_collection_id,
            scene_count=scene_info.get("count", 0),
            scene_dates=dates,
            scene_ids=[str(value) for value in (scene_info.get("ids") or [])],
            first_scene_date=dates[0] if dates else None,
            last_scene_date=dates[-1] if dates else None,
            mean_scene_cloud_percent=metrics.mean_or_none(scene_info.get("clouds") or []),
            cloud_threshold_percent=cloud_threshold,
            cloud_mask_method=mask_method,
            composite_method=composite_method,
            requested_range=date_range,
        )

    def _per_scene_series(
        self,
        collection: ee.ImageCollection,
        geometry: ee.Geometry,
        *,
        scale: int,
        scene_count: int,
        aoi_area_m2: float,
        warnings: list[str],
    ) -> list[TimeSeriesPoint]:
        """One time-series point per scene, in a single Earth Engine round trip.

        Statistics for every scene are computed server-side into a
        ``FeatureCollection`` and evaluated once, rather than looping in Python.
        """
        limit = self._settings.max_timeseries_points
        if scene_count > limit:
            warnings.append(
                f"{scene_count} scenes matched but only the {limit} most recent are "
                "returned. Use a calendar aggregation (weekly/biweekly/monthly) to "
                "cover the whole window."
            )
            collection = collection.limit(limit, "system:time_start", False)

        max_pixels = self._settings.reduce_region_max_pixels
        band = NDVI_BAND

        def _scene_feature(image: ee.Image) -> ee.Feature:
            ndvi = image.select([band])
            stats = ndvi.reduceRegion(
                reducer=ee.Reducer.mean()
                .combine(ee.Reducer.minMax(), sharedInputs=True)
                .combine(ee.Reducer.stdDev(), sharedInputs=True)
                .combine(ee.Reducer.percentile([50]), sharedInputs=True),
                geometry=geometry,
                scale=scale,
                maxPixels=max_pixels,
                bestEffort=False,
            )
            valid_area = (
                ee.Image.pixelArea()
                .updateMask(ndvi.mask())
                .reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=geometry,
                    scale=scale,
                    maxPixels=max_pixels,
                    bestEffort=False,
                )
                .get("area")
            )
            return ee.Feature(
                None,
                {
                    "millis": image.date().millis(),
                    "scene_id": image.get("system:index"),
                    "cloud": image.get("CLOUDY_PIXEL_PERCENTAGE"),
                    "mean": stats.get(f"{band}_mean"),
                    "min": stats.get(f"{band}_min"),
                    "max": stats.get(f"{band}_max"),
                    "median": stats.get(f"{band}_p50"),
                    "std_dev": stats.get(f"{band}_stdDev"),
                    "valid_area_m2": valid_area,
                    "scene_count": 1,
                },
            )

        features = self._gee.evaluate(
            ee.FeatureCollection(collection.map(_scene_feature)),
            label="per-scene NDVI series",
        )
        return [
            _feature_to_point(feature, aoi_area_m2=aoi_area_m2)
            for feature in (features.get("features") or [])
        ]

    def _binned_series(
        self,
        collection: ee.ImageCollection,
        geometry: ee.Geometry,
        *,
        date_range: DateRange,
        aggregation: TemporalAggregation,
        scale: int,
        aoi_area_m2: float,
        composite_method: CompositeMethod,
        warnings: list[str],
    ) -> list[TimeSeriesPoint]:
        """One point per calendar bin, compositing scenes within each bin.

        Compositing inside a bin fills cloud gaps that a single overpass would
        leave, which is the reason to aggregate at all. The cost is temporal
        precision: a monthly point cannot tell you which week a change happened.
        """
        step_days = _AGGREGATION_DAYS[aggregation]
        bin_starts = _bin_start_dates(date_range, step_days)

        limit = self._settings.max_timeseries_points
        if len(bin_starts) > limit:
            warnings.append(
                f"The window produces {len(bin_starts)} {aggregation.value} bins; only the "
                f"first {limit} are returned. Shorten the window or use a coarser "
                "aggregation."
            )
            bin_starts = bin_starts[:limit]

        max_pixels = self._settings.reduce_region_max_pixels
        band = NDVI_BAND
        reducer_name = composite_method.value

        def _bin_feature(start_iso: Any) -> ee.Feature:
            start = ee.Date(start_iso)
            end = start.advance(step_days, "day")
            subset = collection.filterDate(start, end)
            size = subset.size()

            # An empty bin has no bands at all, which would make select() fail.
            # Substitute a fully-masked NDVI image so the reduction returns nulls.
            empty = ee.Image.constant(0).rename(band).toFloat().selfMask()
            composited = ee.Image(
                ee.Algorithms.If(
                    size.gt(0),
                    _reduce_subset(subset, reducer_name, band).select([band]),
                    empty,
                )
            )
            ndvi = composited.select([band]).clip(geometry)

            stats = ndvi.reduceRegion(
                reducer=ee.Reducer.mean()
                .combine(ee.Reducer.minMax(), sharedInputs=True)
                .combine(ee.Reducer.stdDev(), sharedInputs=True)
                .combine(ee.Reducer.percentile([50]), sharedInputs=True),
                geometry=geometry,
                scale=scale,
                maxPixels=max_pixels,
                bestEffort=False,
            )
            valid_area = (
                ee.Image.pixelArea()
                .updateMask(ndvi.mask())
                .reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=geometry,
                    scale=scale,
                    maxPixels=max_pixels,
                    bestEffort=False,
                )
                .get("area")
            )
            return ee.Feature(
                None,
                {
                    "millis": start.millis(),
                    "scene_id": None,
                    "cloud": None,
                    "mean": stats.get(f"{band}_mean"),
                    "min": stats.get(f"{band}_min"),
                    "max": stats.get(f"{band}_max"),
                    "median": stats.get(f"{band}_p50"),
                    "std_dev": stats.get(f"{band}_stdDev"),
                    "valid_area_m2": valid_area,
                    "scene_count": size,
                },
            )

        starts = ee.List([value.isoformat() for value in bin_starts])
        features = self._gee.evaluate(
            ee.FeatureCollection(starts.map(_bin_feature)),
            label=f"{aggregation.value} NDVI series",
        )
        return [
            _feature_to_point(feature, aoi_area_m2=aoi_area_m2)
            for feature in (features.get("features") or [])
        ]

    # ------------------------------------------------------------------
    # Option resolution and validation
    # ------------------------------------------------------------------
    def _validate_window(
        self, date_range: DateRange, warnings: list[str], *, label: str = "date range"
    ) -> None:
        """Enforce window limits and warn about dates outside sensor coverage.

        Raises:
            InvalidRequestError: The window is longer than ``MAX_DATE_RANGE_DAYS``
                or ends before Sentinel-2 existed.
        """
        limit = self._settings.max_date_range_days
        if date_range.days > limit:
            raise InvalidRequestError(
                f"The {label} spans {date_range.days} days, which exceeds the "
                f"{limit}-day limit. Split the request or raise MAX_DATE_RANGE_DAYS.",
                details={"days": date_range.days, "limit_days": limit},
            )

        if date_range.end_date < SENTINEL2_START:
            raise InvalidRequestError(
                f"The {label} ends on {date_range.end_date}, before Sentinel-2 data "
                f"begins ({SENTINEL2_START}). No imagery can exist for it.",
                details={"sentinel2_start": SENTINEL2_START.isoformat()},
            )

        if date_range.start_date < SENTINEL2_START:
            warnings.append(
                f"The {label} starts before Sentinel-2 coverage begins "
                f"({SENTINEL2_START}); the earlier part of the window is empty."
            )

        today = date.today()
        if date_range.end_date > today:
            warnings.append(
                f"The {label} ends in the future ({date_range.end_date}). Only imagery "
                f"acquired up to {today} can exist, and recent scenes may take 1-3 days "
                "to appear in the archive."
            )

    def _resolve_mask_method(
        self,
        options: AnalysisOptions,
        date_range: DateRange,
        warnings: list[str],
    ) -> CloudMaskMethod:
        """Choose the cloud-mask method, downgrading gracefully when unsupported.

        Cloud Score+ only covers acquisitions from 2017-06-27 onward. Requesting
        it for an earlier window would silently mask everything, so we fall back
        to SCL and say so.
        """
        requested = options.cloud_mask_method or CloudMaskMethod.CS_PLUS

        if requested is CloudMaskMethod.CS_PLUS and not self._gee.cloud_score_plus_supported(
            date_range
        ):
            warnings.append(
                f"Cloud Score+ only covers acquisitions from {CLOUD_SCORE_PLUS_START} "
                "onward, so the Scene Classification Layer (SCL) mask was used instead "
                "for this window."
            )
            return CloudMaskMethod.SCL

        if requested is CloudMaskMethod.QA60:
            warnings.append(
                "QA60 is a coarse 60 m legacy bitmask that does not detect cloud shadow "
                "and is empty for some acquisition dates. Prefer 'cs_plus' or 'scl'."
            )
        elif requested is CloudMaskMethod.NONE:
            warnings.append(
                "Per-pixel cloud masking is disabled. Cloud, cirrus and shadow pixels "
                "are included in the statistics, which will depress NDVI. Diagnostic "
                "use only."
            )

        return requested

    @staticmethod
    def _warn_on_composite_choice(method: CompositeMethod, warnings: list[str]) -> None:
        """Flag composite choices with known interpretive bias."""
        if method is CompositeMethod.GREENEST:
            warnings.append(
                "The 'greenest pixel' composite takes each pixel's maximum NDVI over the "
                "window, which biases the result upward and can hide stress that "
                "developed later. Use 'median' or 'most_recent' to assess condition."
            )
        elif method is CompositeMethod.MEAN:
            warnings.append(
                "The mean composite is more sensitive to unmasked cloud and shadow than the median."
            )

    @staticmethod
    def _change_warnings(
        *,
        comparable_m2: float,
        aoi_area_m2: float,
        baseline_scenes: int,
        recent_scenes: int,
    ) -> list[str]:
        """Caveats specific to a two-period comparison."""
        warnings: list[str] = []
        if aoi_area_m2 > 0:
            fraction = comparable_m2 / aoi_area_m2
            if fraction < 0.5:
                warnings.append(
                    f"Only {fraction * 100:.0f}% of the AOI was cloud-free in both periods, "
                    "so the change statistics describe that subset rather than the whole "
                    "field."
                )
        if baseline_scenes == 1 or recent_scenes == 1:
            warnings.append(
                "At least one period is represented by a single scene, so the comparison "
                "includes that scene's atmospheric and viewing-geometry conditions as "
                "well as any real change."
            )
        return warnings

    @staticmethod
    def _largest_gap_warning(points: list[TimeSeriesPoint]) -> str | None:
        """Warn when consecutive observations are far apart.

        Sentinel-2's nominal revisit is 2-5 days, so a gap over three weeks
        means a sustained cloudy period during which anything could have
        happened to the crop unobserved.
        """
        if len(points) < 2:
            return None

        parsed = [metrics._parse_iso_date(point.date) for point in points]
        valid = [moment for moment in parsed if moment is not None]
        if len(valid) < 2:
            return None

        gaps = [(valid[index + 1] - valid[index]).days for index in range(len(valid) - 1)]
        largest = max(gaps)
        if largest < 21:
            return None
        return (
            f"The largest gap between usable observations is {largest} days. Crop "
            "condition can change substantially inside a gap that long, and the trend "
            "line interpolates straight through it."
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------
def _reduce_subset(subset: ee.ImageCollection, reducer_name: str, band: str) -> ee.Image:
    """Composite a bin's scenes using the requested reduction.

    ``greenest`` and ``most_recent`` both need the NDVI band, which the caller
    guarantees is present.
    """
    if reducer_name == CompositeMethod.MEAN.value:
        return subset.mean()
    if reducer_name == CompositeMethod.GREENEST.value:
        return subset.qualityMosaic(band)
    if reducer_name == CompositeMethod.MOST_RECENT.value:
        return subset.mosaic()
    return subset.median()


def _feature_to_point(feature: dict[str, Any], *, aoi_area_m2: float) -> TimeSeriesPoint:
    """Convert one evaluated Earth Engine feature into a time-series point."""
    properties = feature.get("properties") or {}

    valid_area = properties.get("valid_area_m2")
    valid_fraction: float | None = None
    if valid_area is not None and aoi_area_m2 > 0:
        valid_fraction = round(min(max(float(valid_area) / aoi_area_m2, 0.0), 1.0), 4)

    iso_date = metrics.epoch_ms_to_date_str(properties.get("millis")) or ""
    scene_count_raw = properties.get("scene_count")

    return TimeSeriesPoint(
        date=iso_date,
        mean_ndvi=_opt_round(properties.get("mean")),
        min_ndvi=_opt_round(properties.get("min")),
        max_ndvi=_opt_round(properties.get("max")),
        median_ndvi=_opt_round(properties.get("median")),
        std_dev_ndvi=_opt_round(properties.get("std_dev")),
        valid_pixel_fraction=valid_fraction,
        scene_count=int(scene_count_raw) if scene_count_raw is not None else 1,
        scene_cloud_percent=_opt_round(properties.get("cloud"), digits=2),
        scene_id=properties.get("scene_id"),
    )


def _opt_round(value: Any, *, digits: int = 4) -> float | None:
    """Round a possibly-None, possibly-non-numeric Earth Engine value."""
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _bin_start_dates(date_range: DateRange, step_days: int) -> list[date]:
    """Generate bin start dates covering the window at a fixed step."""
    starts: list[date] = []
    cursor = date_range.start_date
    while cursor <= date_range.end_date:
        starts.append(cursor)
        cursor = cursor + timedelta(days=step_days)
    return starts


def _windows_overlap(first: DateRange, second: DateRange) -> bool:
    """True when two inclusive date windows share at least one day."""
    return first.start_date <= second.end_date and second.start_date <= first.end_date


# ---------------------------------------------------------------------------
# Plain factory
# ---------------------------------------------------------------------------
def get_analysis_service() -> AnalysisService:
    """Build an analysis service backed by the process-wide Earth Engine client.

    For scripts and notebooks. HTTP routes use
    :func:`app.api.dependencies.analysis_service` instead, so that tests can
    substitute the Earth Engine client.
    """
    return AnalysisService()
