import type { ReactNode } from 'react'
import type { ApiError } from '@/services/apiClient'

interface ErrorStateProps {
  error: ApiError
  onRetry?: () => void
  /** Extra advice from the calling panel, e.g. "try a wider date range". */
  children?: ReactNode
}

/**
 * Advice keyed on the backend's machine-readable error code.
 *
 * Branching on `code` rather than HTTP status is what makes this useful: a 503
 * that means "credentials missing" and a 502 that means "Earth Engine hiccuped"
 * need completely different next steps from the person looking at the screen.
 */
function guidanceFor(error: ApiError): { title: string; advice: string[] } {
  switch (error.code) {
    case 'no_imagery':
      return {
        title: 'No usable Sentinel-2 imagery',
        advice: [
          'Widen the date range — Sentinel-2 revisits every ~5 days, and monsoon or winter cloud can hide a field for weeks.',
          'Raise the cloud-cover limit to admit partly cloudy scenes (per-pixel masking still removes the cloudy parts).',
          'Confirm the area is on land and within Sentinel-2 coverage.',
          'Cloud Score+ masking only covers dates from 27 June 2017 onward.',
        ],
      }
    case 'invalid_aoi':
      return {
        title: 'The area of interest was rejected',
        advice: [
          'Redraw the field as a simple, non-self-intersecting polygon.',
          'Check the area against the server limit shown in the sidebar — very large areas are refused to protect the Earth Engine quota.',
          'If you pasted GeoJSON, it must be a single Polygon, MultiPolygon or Point in EPSG:4326 (longitude first).',
        ],
      }
    case 'invalid_request':
      return {
        title: 'The request was not valid',
        advice: [
          'Check the dates are in order and the window is within the server’s maximum length.',
          'NDVI class thresholds must be four values in ascending order, each between −1 and 1.',
        ],
      }
    case 'earth_engine_auth_error':
      return {
        title: 'Earth Engine is not authenticated',
        advice:
          error.remediation.length > 0
            ? error.remediation
            : [
                'The backend started but has no usable Earth Engine credentials.',
                'Follow docs/SETUP.md, then restart the backend and run the connection test.',
              ],
      }
    case 'configuration_error':
      return {
        title: 'The server is misconfigured',
        advice:
          error.remediation.length > 0
            ? error.remediation
            : ['Check backend/.env against .env.example, then restart the backend.'],
      }
    case 'earth_engine_error':
      return {
        title: 'Earth Engine could not complete the computation',
        advice: [
          'This is usually transient — retry.',
          'If it repeats, reduce the area, shorten the date range, or increase the analysis scale (e.g. 20 m instead of 10 m) to lower the computation size.',
        ],
      }
    case 'network_error':
      return {
        title: 'Cannot reach the CropSense API',
        advice: [
          'Start the backend: uvicorn app.main:app --reload --port 8000 (from the backend directory).',
          'If the backend runs on a different port, set VITE_DEV_PROXY_TARGET and restart the dev server.',
        ],
      }
    case 'timeout':
      return {
        title: 'The request timed out',
        advice: [
          'Shrink the area of interest or shorten the date range.',
          'Increase the analysis scale — 20 m or 30 m reduces the pixel count dramatically with little effect on field-level means.',
        ],
      }
    default:
      return {
        title: 'Something went wrong',
        advice: ['Check the backend log for the full traceback and request ID.'],
      }
  }
}

/** Error panel with a machine code, a readable message and concrete next steps. */
export function ErrorState({ error, onRetry, children }: ErrorStateProps) {
  const { title, advice } = guidanceFor(error)

  return (
    <div className="state state--error" role="alert">
      <div className="state__text">
        <p className="state__title">
          {title}
          <code className="state__code">{error.code}</code>
        </p>
        <p className="state__message">{error.message}</p>

        {advice.length > 0 ? (
          <>
            <p className="state__detail">What to try:</p>
            <ul className="state__list">
              {advice.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </>
        ) : null}

        {children}
      </div>

      {onRetry && error.isRetryable ? (
        <button type="button" className="button button--primary" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  )
}
