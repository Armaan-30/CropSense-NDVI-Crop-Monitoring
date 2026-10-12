/**
 * Typed wrappers for every CropSense endpoint the dashboard uses.
 *
 * Components never build URLs or touch `fetch` - they call these functions, so
 * a backend path change is a one-file edit and every call site keeps its types.
 */

import { apiGet, apiPost } from '@/services/apiClient'
import type {
  ChangeDetectionRequest,
  ChangeDetectionResponse,
  ConfigResponse,
  GEETestResponse,
  HealthResponse,
  NDVIAnalyzeRequest,
  NDVIAnalyzeResponse,
  TimeSeriesRequest,
  TimeSeriesResponse,
} from '@/types/api'

/** Paths kept in one place so they match `backend/app/api/router.py`. */
const ROUTES = {
  health: '/health',
  config: '/api/system/config',
  geeTest: '/api/system/gee-test',
  analyze: '/api/ndvi/analyze',
  timeseries: '/api/ndvi/timeseries',
  change: '/api/ndvi/change',
} as const

interface CallOptions {
  signal?: AbortSignal
}

/**
 * API liveness plus Earth Engine readiness.
 *
 * Returns HTTP 200 even when Earth Engine is unusable, so check
 * `response.status === 'degraded'` and surface `earth_engine.remediation`.
 * Cheap - spends no Earth Engine round trip.
 */
export function fetchHealth(options?: CallOptions): Promise<HealthResponse> {
  // Health is polled; a hung backend should not tie up the UI for two minutes.
  return apiGet<HealthResponse>(ROUTES.health, { ...options, timeoutMs: 10_000 })
}

/**
 * Server processing defaults, so the UI mirrors the backend instead of
 * hard-coding a second copy of the thresholds and palette.
 */
export function fetchServerConfig(options?: CallOptions): Promise<ConfigResponse> {
  return apiGet<ConfigResponse>(ROUTES.config, { ...options, timeoutMs: 15_000 })
}

/**
 * Run a real (small) Earth Engine computation.
 *
 * Always resolves with HTTP 200; inspect `success`. Takes a real round trip, so
 * only call it when the user asks for a connection test.
 */
export function testEarthEngine(options?: CallOptions): Promise<GEETestResponse> {
  return apiGet<GEETestResponse>(ROUTES.geeTest, { ...options, timeoutMs: 60_000 })
}

/** NDVI snapshot: statistics, health classes and signed map layers. */
export function analyzeNDVI(
  request: NDVIAnalyzeRequest,
  options?: CallOptions,
): Promise<NDVIAnalyzeResponse> {
  return apiPost<NDVIAnalyzeResponse>(ROUTES.analyze, request, options)
}

/** Mean NDVI over time plus an ordinary-least-squares trend. */
export function fetchTimeSeries(
  request: TimeSeriesRequest,
  options?: CallOptions,
): Promise<TimeSeriesResponse> {
  return apiPost<TimeSeriesResponse>(ROUTES.timeseries, request, options)
}

/** Difference two periods and screen for potential vegetation stress. */
export function detectChange(
  request: ChangeDetectionRequest,
  options?: CallOptions,
): Promise<ChangeDetectionResponse> {
  return apiPost<ChangeDetectionResponse>(ROUTES.change, request, options)
}
