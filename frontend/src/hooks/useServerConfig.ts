/**
 * Server configuration and Earth Engine readiness.
 *
 * Both are fetched once when the dashboard mounts. `/api/system/config` is the
 * single source of truth for default thresholds, the NDVI palette and the AOI
 * and date-range limits, so the UI does not carry a second copy that can drift
 * from the backend.
 */

import { useCallback, useEffect } from 'react'
import { useAsyncTask } from '@/hooks/useAsyncTask'
import { fetchHealth, fetchServerConfig, testEarthEngine } from '@/services/ndviApi'
import type { ConfigResponse, GEETestResponse, HealthResponse } from '@/types/api'

/** Fetch `/api/system/config` on mount. */
export function useServerConfig() {
  const task = useAsyncTask<[], ConfigResponse>(
    useCallback((signal: AbortSignal) => fetchServerConfig({ signal }), []),
  )

  useEffect(() => {
    void task.run()
    // `run` is stable; re-running on every render would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return task
}

/**
 * Fetch `/health` on mount and expose a manual refresh.
 *
 * Not polled. Earth Engine credentials do not appear on their own while the
 * page is open - they appear after the operator does something and reloads or
 * clicks refresh, so a background poll would only add noise.
 */
export function useHealthStatus() {
  const task = useAsyncTask<[], HealthResponse>(
    useCallback((signal: AbortSignal) => fetchHealth({ signal }), []),
  )

  useEffect(() => {
    void task.run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return task
}

/**
 * Live Earth Engine connectivity test, run only on explicit user request.
 *
 * Spends a real Earth Engine round trip, so this is never automatic.
 */
export function useEarthEngineTest() {
  return useAsyncTask<[], GEETestResponse>(
    useCallback((signal: AbortSignal) => testEarthEngine({ signal }), []),
  )
}
