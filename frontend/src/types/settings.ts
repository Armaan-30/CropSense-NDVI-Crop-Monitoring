/**
 * Dashboard form state.
 *
 * One flat object holds every processing choice the user can make, so the three
 * analysis modes share settings: change the cloud mask once and the snapshot,
 * the time series and the comparison all use it. Request bodies are derived from
 * this in `services/requestBuilders.ts`.
 *
 * The dashboard stores only the user's *overrides* and derives the effective
 * settings from `/api/system/config` on each render - see `effectiveSettings`.
 * That keeps the server as the single source of truth for defaults.
 */

import type {
  CloudMaskMethod,
  CompositeMethod,
  ConfigResponse,
  DateRange,
  TemporalAggregation,
} from '@/types/api'
import { addDays, today } from '@/utils/dates'

export interface AnalysisSettings {
  /** Outward buffer applied to the AOI, metres. Also turns a Point into a disc. */
  bufferM: number
  /** Scene-level cloud-cover cut-off, 0-100. */
  cloudThreshold: number
  cloudMaskMethod: CloudMaskMethod
  compositeMethod: CompositeMethod
  /** Analysis scale in metres, 10-1000. */
  scaleM: number
  /** Cloud Score+ `cs_cdf` cut-off, 0-1. Only used when the mask is `cs_plus`. */
  cloudScorePlusThreshold: number
  includeTrueColor: boolean
  /** Four ascending NDVI class boundaries. */
  thresholds: number[]
  /**
   * Whether the user edited the thresholds.
   *
   * Drives whether we send them at all: omitting them lets the server report
   * `thresholds_source: "server_default"`, which is the honest label for an
   * uncalibrated run.
   */
  thresholdsAreCustom: boolean
  /** Minimum NDVI drop treated as a decline, for change detection. */
  declineThreshold: number
  /** Time step for the temporal series. */
  aggregation: TemporalAggregation
  /** Drop time steps with less cloud-free coverage than this, 0-1. */
  minValidFraction: number
}

/** Threshold set used before `/api/system/config` has been read. */
const FALLBACK_THRESHOLDS = [0.2, 0.4, 0.6, 0.8]

/**
 * Settings used before the server config arrives.
 *
 * These mirror the backend defaults. They are a bootstrap value only - the
 * dashboard replaces them with the real server config as soon as it loads, so
 * there is one authoritative source of defaults rather than two that can drift.
 */
export function fallbackSettings(): AnalysisSettings {
  return {
    bufferM: 0,
    cloudThreshold: 30,
    cloudMaskMethod: 'cs_plus',
    compositeMethod: 'median',
    scaleM: 10,
    cloudScorePlusThreshold: 0.6,
    includeTrueColor: true,
    thresholds: [...FALLBACK_THRESHOLDS],
    thresholdsAreCustom: false,
    declineThreshold: 0.15,
    aggregation: 'scene',
    minValidFraction: 0.1,
  }
}

/** Rebuild settings from the server's own defaults. */
export function serverSettings(config: ConfigResponse): AnalysisSettings {
  return {
    ...fallbackSettings(),
    cloudMaskMethod: config.default_cloud_mask_method,
    compositeMethod: config.default_composite_method,
    scaleM: config.default_scale_m,
    declineThreshold: config.default_decline_threshold,
    thresholds: [...config.default_ndvi_class_thresholds],
  }
}

/**
 * The settings the user has actually changed.
 *
 * Only the edits are stored, never a full copy of the server's defaults. The
 * effective settings are derived on every render, which removes the whole class
 * of bug where the config arrives after the user has already touched a control
 * and one of the two silently wins.
 */
export type SettingsOverrides = Partial<AnalysisSettings>

/** Server defaults with the user's edits layered on top. */
export function effectiveSettings(
  config: ConfigResponse | null,
  overrides: SettingsOverrides,
): AnalysisSettings {
  const base = config ? serverSettings(config) : fallbackSettings()
  return { ...base, ...overrides }
}

/** Default date windows for each analysis mode. */
export function defaultRanges(): {
  snapshot: DateRange
  series: DateRange
  baseline: DateRange
  recent: DateRange
} {
  const end = today()
  return {
    // One month usually contains several Sentinel-2 overpasses.
    snapshot: { start_date: addDays(end, -29), end_date: end },
    // A full year shows the whole season shape, not just the current state.
    series: { start_date: addDays(end, -364), end_date: end },
    // Two non-overlapping 30-day windows, separated by a month: long enough for
    // a real change in canopy, short enough that each still composites cleanly.
    baseline: { start_date: addDays(end, -89), end_date: addDays(end, -60) },
    recent: { start_date: addDays(end, -29), end_date: end },
  }
}
