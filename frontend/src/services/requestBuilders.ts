/**
 * Turn dashboard state into API request bodies.
 *
 * Kept out of the components so there is exactly one place that decides what
 * gets sent - including the deliberate omissions:
 *
 * - `ndvi_class_thresholds` is sent **only** when the user edited it. Omitting it
 *   lets the server answer `thresholds_source: "server_default"`, which is the
 *   honest label for a run on uncalibrated generic thresholds.
 * - `cloud_score_plus_threshold` is sent only when Cloud Score+ is the active
 *   mask, since it means nothing otherwise.
 *
 * The backend sets `extra="forbid"` on `AnalysisOptions`, so anything not in the
 * schema is a 422 rather than a silently ignored field.
 */

import type {
  AnalysisOptions,
  AOIGeometry,
  ChangeDetectionRequest,
  DateRange,
  NDVIAnalyzeRequest,
  TimeSeriesRequest,
} from '@/types/api'
import type { AnalysisSettings } from '@/types/settings'

function buildOptions(settings: AnalysisSettings, includeTrueColor: boolean): AnalysisOptions {
  const options: AnalysisOptions = {
    cloud_mask_method: settings.cloudMaskMethod,
    composite_method: settings.compositeMethod,
    scale_m: settings.scaleM,
    include_true_color_layer: includeTrueColor,
  }

  if (settings.thresholdsAreCustom) {
    options.ndvi_class_thresholds = [...settings.thresholds]
  }
  if (settings.cloudMaskMethod === 'cs_plus') {
    options.cloud_score_plus_threshold = settings.cloudScorePlusThreshold
  }

  return options
}

export function buildAnalyzeRequest(
  aoi: AOIGeometry,
  range: DateRange,
  settings: AnalysisSettings,
): NDVIAnalyzeRequest {
  return {
    aoi,
    start_date: range.start_date,
    end_date: range.end_date,
    buffer_m: settings.bufferM,
    cloud_threshold: settings.cloudThreshold,
    options: buildOptions(settings, settings.includeTrueColor),
  }
}

export function buildTimeSeriesRequest(
  aoi: AOIGeometry,
  range: DateRange,
  settings: AnalysisSettings,
): TimeSeriesRequest {
  return {
    aoi,
    start_date: range.start_date,
    end_date: range.end_date,
    buffer_m: settings.bufferM,
    cloud_threshold: settings.cloudThreshold,
    aggregation: settings.aggregation,
    min_valid_fraction: settings.minValidFraction,
    // A time series renders no tiles, so asking for an RGB layer would only
    // spend Earth Engine time on something nothing displays.
    options: buildOptions(settings, false),
  }
}

export function buildChangeRequest(
  aoi: AOIGeometry,
  baseline: DateRange,
  recent: DateRange,
  settings: AnalysisSettings,
): ChangeDetectionRequest {
  return {
    aoi,
    baseline_start_date: baseline.start_date,
    baseline_end_date: baseline.end_date,
    recent_start_date: recent.start_date,
    recent_end_date: recent.end_date,
    buffer_m: settings.bufferM,
    cloud_threshold: settings.cloudThreshold,
    decline_threshold: settings.declineThreshold,
    options: buildOptions(settings, settings.includeTrueColor),
  }
}
