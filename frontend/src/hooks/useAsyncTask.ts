/**
 * Generic async-request state machine.
 *
 * Every panel in the dashboard needs the same four things: is it loading, did
 * it fail, what came back, and how do I re-run it. Rather than repeat that in
 * five hooks, they all build on this one.
 *
 * Two behaviours matter for this app specifically:
 *
 * - **Abort on supersede and unmount.** Earth Engine calls routinely run for
 *   20-40 seconds. If the user redraws the AOI mid-request, the stale response
 *   must not overwrite the new one, and it must not fire `setState` after the
 *   component is gone.
 * - **Elapsed time.** A spinner with no feedback for 40 seconds looks broken.
 *   Exposing elapsed time lets the loading state say "still computing (18s)".
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '@/services/apiClient'

export interface AsyncTaskState<TResult> {
  data: TResult | null
  error: ApiError | null
  isLoading: boolean
  /** Milliseconds since the in-flight request started; 0 when idle. */
  elapsedMs: number
  /** True once a request has completed at least once (success or failure). */
  hasRun: boolean
}

export interface AsyncTask<TArgs extends unknown[], TResult> extends AsyncTaskState<TResult> {
  /** Start (or restart) the task. Resolves with the result, or `null` on failure. */
  run: (...args: TArgs) => Promise<TResult | null>
  /** Cancel any in-flight request without clearing the last result. */
  cancel: () => void
  /** Cancel and clear all state. */
  reset: () => void
}

/**
 * @param task Receives an `AbortSignal` first so it can pass it to the API
 *   layer, followed by whatever arguments the caller supplies. Must be stable
 *   (module-level function, or wrapped in `useCallback`).
 */
export function useAsyncTask<TArgs extends unknown[], TResult>(
  task: (signal: AbortSignal, ...args: TArgs) => Promise<TResult>,
): AsyncTask<TArgs, TResult> {
  const [data, setData] = useState<TResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [hasRun, setHasRun] = useState(false)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [elapsedMs, setElapsedMs] = useState(0)

  const controllerRef = useRef<AbortController | null>(null)
  /** Guards against a resolved-but-superseded request writing state. */
  const requestIdRef = useRef(0)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      controllerRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (startedAt === null) return
    const timer = window.setInterval(() => setElapsedMs(Date.now() - startedAt), 250)
    return () => window.clearInterval(timer)
  }, [startedAt])

  const run = useCallback(
    async (...args: TArgs): Promise<TResult | null> => {
      controllerRef.current?.abort()
      const controller = new AbortController()
      controllerRef.current = controller

      requestIdRef.current += 1
      const requestId = requestIdRef.current

      setIsLoading(true)
      setError(null)
      setStartedAt(Date.now())
      setElapsedMs(0)

      try {
        const result = await task(controller.signal, ...args)
        if (!mountedRef.current || requestId !== requestIdRef.current) return null
        setData(result)
        return result
      } catch (caught) {
        if (!mountedRef.current || requestId !== requestIdRef.current) return null
        const apiError =
          caught instanceof ApiError
            ? caught
            : new ApiError('internal_error', caught instanceof Error ? caught.message : String(caught))
        // A deliberate cancellation is not a failure worth showing.
        if (apiError.code !== 'aborted') setError(apiError)
        return null
      } finally {
        if (mountedRef.current && requestId === requestIdRef.current) {
          setIsLoading(false)
          setStartedAt(null)
          setHasRun(true)
        }
      }
    },
    [task],
  )

  const cancel = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setIsLoading(false)
    setStartedAt(null)
  }, [])

  const reset = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    requestIdRef.current += 1
    setData(null)
    setError(null)
    setIsLoading(false)
    setStartedAt(null)
    setElapsedMs(0)
    setHasRun(false)
  }, [])

  return { data, error, isLoading, elapsedMs, hasRun, run, cancel, reset }
}
