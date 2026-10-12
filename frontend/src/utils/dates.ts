/**
 * Date helpers for the range pickers.
 *
 * All dates crossing the API boundary are `YYYY-MM-DD` strings. We deliberately
 * avoid `toISOString()` for that conversion: it converts to UTC first, so on a
 * machine east of Greenwich "today" can come back as yesterday. These helpers
 * read the *local* calendar fields instead, matching what the user sees in the
 * date input.
 */

/** Serialise a `Date` to `YYYY-MM-DD` using local calendar fields. */
export function toISODate(date: Date): string {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** Parse a `YYYY-MM-DD` string as a local-midnight `Date`. */
export function fromISODate(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number)
  // noUncheckedIndexedAccess: destructuring a split() result can be undefined.
  if (year === undefined || month === undefined || day === undefined) {
    return new Date(NaN)
  }
  return new Date(year, month - 1, day)
}

/** Today, as `YYYY-MM-DD`. */
export function today(): string {
  return toISODate(new Date())
}

/** Shift an ISO date by a number of days (negative shifts backwards). */
export function addDays(iso: string, days: number): string {
  const date = fromISODate(iso)
  if (Number.isNaN(date.getTime())) return iso
  date.setDate(date.getDate() + days)
  return toISODate(date)
}

/** Inclusive day count between two ISO dates; 0 if either is unparseable. */
export function daysBetween(startISO: string, endISO: string): number {
  const start = fromISODate(startISO)
  const end = fromISODate(endISO)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 0
  const msPerDay = 24 * 60 * 60 * 1000
  return Math.round((end.getTime() - start.getTime()) / msPerDay) + 1
}

/** True when `endISO` is on or after `startISO`. */
export function isOrderedRange(startISO: string, endISO: string): boolean {
  const start = fromISODate(startISO)
  const end = fromISODate(endISO)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return false
  return end.getTime() >= start.getTime()
}

/**
 * A window ending today and covering `days` days.
 *
 * Used for the default date range. Sentinel-2's revisit is 5 days at the
 * equator (two satellites), so a 30-day default window is wide enough to
 * contain several overpasses even with moderate cloud.
 */
export function recentWindow(days: number): { start_date: string; end_date: string } {
  const end = today()
  return { start_date: addDays(end, -(days - 1)), end_date: end }
}

/**
 * First date with usable coverage for the chosen cloud mask.
 *
 * Sentinel-2 L2A surface reflectance in Earth Engine starts 2017-03-28, and
 * Cloud Score+ coverage starts 2017-06-27. Offering earlier dates in the picker
 * would only produce `no_imagery` errors.
 */
export const EARLIEST_L2A_DATE = '2017-03-28'
export const EARLIEST_CLOUD_SCORE_PLUS_DATE = '2017-06-27'

/** Earliest selectable date for a given cloud-mask method. */
export function earliestDateFor(cloudMaskMethod: string): string {
  return cloudMaskMethod === 'cs_plus' ? EARLIEST_CLOUD_SCORE_PLUS_DATE : EARLIEST_L2A_DATE
}
