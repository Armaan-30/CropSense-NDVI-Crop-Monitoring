/**
 * The three analysis hooks, one per NDVI endpoint.
 *
 * Each is a thin `useAsyncTask` binding. They are separate hooks rather than one
 * parameterised hook so the dashboard can hold all three results at once - the
 * user can look at a snapshot, then the time series, then a comparison, without
 * any of them clearing the others.
 */

import { useCallback } from 'react'
import { useAsyncTask } from '@/hooks/useAsyncTask'
import { analyzeNDVI, detectChange, fetchTimeSeries } from '@/services/ndviApi'
import type {
  ChangeDetectionRequest,
  ChangeDetectionResponse,
  NDVIAnalyzeRequest,
  NDVIAnalyzeResponse,
  TimeSeriesRequest,
  TimeSeriesResponse,
} from '@/types/api'

/** `POST /api/ndvi/analyze` - NDVI snapshot for one date window. */
export function useNDVIAnalysis() {
  return useAsyncTask<[NDVIAnalyzeRequest], NDVIAnalyzeResponse>(
    useCallback(
      (signal: AbortSignal, request: NDVIAnalyzeRequest) => analyzeNDVI(request, { signal }),
      [],
    ),
  )
}

/** `POST /api/ndvi/timeseries` - NDVI over time plus a linear trend. */
export function useTimeSeries() {
  return useAsyncTask<[TimeSeriesRequest], TimeSeriesResponse>(
    useCallback(
      (signal: AbortSignal, request: TimeSeriesRequest) => fetchTimeSeries(request, { signal }),
      [],
    ),
  )
}

/** `POST /api/ndvi/change` - two-period comparison and stress screening. */
export function useChangeDetection() {
  return useAsyncTask<[ChangeDetectionRequest], ChangeDetectionResponse>(
    useCallback(
      (signal: AbortSignal, request: ChangeDetectionRequest) => detectChange(request, { signal }),
      [],
    ),
  )
}
