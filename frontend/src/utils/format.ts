/**
 * Display formatters.
 *
 * Two rules run through this module:
 *
 * 1. `null` is never rendered as `0`. A missing NDVI mean means "no cloud-free
 *    pixels", which is completely different from "NDVI is zero". Every formatter
 *    accepts `null | undefined` and returns a dash.
 * 2. Precision matches the measurement. NDVI is reported to 3 decimals (the
 *    difference between 0.61 and 0.62 is real); areas to 2; percentages to 1.
 */

/** Placeholder for values the backend could not compute. */
export const NO_DATA = '—'

function isMissing(value: number | null | undefined): value is null | undefined {
  return value === null || value === undefined || !Number.isFinite(value)
}

/** Format an NDVI value in [-1, 1]. */
export function formatNDVI(value: number | null | undefined, digits = 3): string {
  if (isMissing(value)) return NO_DATA
  return value.toFixed(digits)
}

/** Format a signed NDVI difference, always with an explicit sign. */
export function formatNDVIDelta(value: number | null | undefined, digits = 3): string {
  if (isMissing(value)) return NO_DATA
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(digits)}`
}

/** Format a hectare area, switching to km² once hectares get unwieldy. */
export function formatArea(hectares: number | null | undefined): string {
  if (isMissing(hectares)) return NO_DATA
  if (hectares >= 10_000) return `${(hectares / 100).toFixed(1)} km²`
  if (hectares < 1) return `${(hectares * 10_000).toFixed(0)} m²`
  return `${hectares.toFixed(2)} ha`
}

/** Format an already-0-100 percentage. */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (isMissing(value)) return NO_DATA
  return `${value.toFixed(digits)}%`
}

/** Format a 0-1 fraction as a percentage. */
export function formatFraction(value: number | null | undefined, digits = 1): string {
  if (isMissing(value)) return NO_DATA
  return `${(value * 100).toFixed(digits)}%`
}

/** Format a plain integer count with thousands separators. */
export function formatCount(value: number | null | undefined): string {
  if (isMissing(value)) return NO_DATA
  return value.toLocaleString()
}

/** Format a duration given in milliseconds. */
export function formatDuration(ms: number | null | undefined): string {
  if (isMissing(ms)) return NO_DATA
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

/**
 * Format an ISO date (or datetime) for display.
 *
 * Falls back to the raw string if it is not parseable - showing the server's
 * value is more useful than showing "Invalid Date".
 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return NO_DATA
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/** Format an ISO timestamp with time, for "computed at" style captions. */
export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return NO_DATA
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Render a class's NDVI bounds as a readable interval.
 *
 * `null` bounds mean unbounded, which the backend uses for the first and last
 * class. Bounds are `[min, max)` - inclusive lower, exclusive upper.
 */
export function formatNDVIRange(min: number | null, max: number | null): string {
  const low = min === null ? '−1' : min.toFixed(2)
  const high = max === null ? '1' : max.toFixed(2)
  return `${low} – ${high}`
}

/** Human-readable label for a cloud-mask method. */
export function cloudMaskLabel(method: string): string {
  switch (method) {
    case 'cs_plus':
      return 'Cloud Score+'
    case 'scl':
      return 'Scene Classification Layer'
    case 'qa60':
      return 'QA60 bitmask (legacy)'
    case 'none':
      return 'No pixel masking'
    default:
      return method
  }
}

/** Human-readable label for a composite method. */
export function compositeLabel(method: string): string {
  switch (method) {
    case 'median':
      return 'Median composite'
    case 'mean':
      return 'Mean composite'
    case 'greenest':
      return 'Greenest pixel'
    case 'most_recent':
      return 'Most recent pixel'
    default:
      return method
  }
}

/** Human-readable label for a temporal aggregation step. */
export function aggregationLabel(aggregation: string): string {
  switch (aggregation) {
    case 'scene':
      return 'Per scene'
    case 'weekly':
      return 'Weekly'
    case 'biweekly':
      return 'Fortnightly'
    case 'monthly':
      return 'Monthly'
    default:
      return aggregation
  }
}
