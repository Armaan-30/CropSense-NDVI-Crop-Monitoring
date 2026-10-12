/**
 * Environment-derived application settings.
 *
 * Parsed once at module load so a malformed value shows up immediately and in
 * one place, rather than as a `NaN` centre that silently sends Leaflet to the
 * middle of nowhere.
 */

/** Fallback map centre: Maharashtra state overview; users can zoom to their field. */
const FALLBACK_CENTER_LAT = 19.7515
const FALLBACK_CENTER_LNG = 75.7139
const FALLBACK_ZOOM = 7
const FALLBACK_TIMEOUT_MS = 120_000

function readNumber(raw: string | undefined, fallback: number, label: string): number {
  if (raw === undefined || raw.trim() === '') return fallback
  const parsed = Number(raw)
  if (!Number.isFinite(parsed)) {
    console.warn(`[cropsense] ${label} is not a number ("${raw}"); using ${fallback}.`)
    return fallback
  }
  return parsed
}

/**
 * Base URL for API calls.
 *
 * Empty string means "same origin", which is what we want in development (Vite
 * proxies `/api` and `/health` to the backend) and for a deployment that serves
 * the built bundle behind the same reverse proxy as the API. A trailing slash
 * is stripped so callers can always concatenate a leading-slash path.
 */
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

export const REQUEST_TIMEOUT_MS: number = readNumber(
  import.meta.env.VITE_REQUEST_TIMEOUT_MS,
  FALLBACK_TIMEOUT_MS,
  'VITE_REQUEST_TIMEOUT_MS',
)

export const DEFAULT_MAP_CENTER: readonly [number, number] = [
  readNumber(
    import.meta.env.VITE_DEFAULT_MAP_CENTER_LAT,
    FALLBACK_CENTER_LAT,
    'VITE_DEFAULT_MAP_CENTER_LAT',
  ),
  readNumber(
    import.meta.env.VITE_DEFAULT_MAP_CENTER_LNG,
    FALLBACK_CENTER_LNG,
    'VITE_DEFAULT_MAP_CENTER_LNG',
  ),
]

export const DEFAULT_MAP_ZOOM: number = readNumber(
  import.meta.env.VITE_DEFAULT_MAP_ZOOM,
  FALLBACK_ZOOM,
  'VITE_DEFAULT_MAP_ZOOM',
)
