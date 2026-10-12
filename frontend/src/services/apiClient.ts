/**
 * Low-level HTTP client for the CropSense API.
 *
 * Everything the app knows about transport lives here: base URL resolution,
 * timeouts, JSON encoding, and - most importantly - turning the backend's
 * uniform `{code, message, details}` error envelope into a typed
 * {@link ApiError} that the UI can branch on.
 *
 * The UI should branch on `error.code`, never on the HTTP status. A 503 with
 * code `earth_engine_auth_error` needs setup instructions; a 502 with
 * `earth_engine_error` needs a retry. Same family of status, very different
 * advice.
 */

import { API_BASE_URL, REQUEST_TIMEOUT_MS } from '@/utils/env'
import type { ErrorResponse } from '@/types/api'

/** Error codes the backend can return. Mirrors `app/core/exceptions.py`. */
export type ApiErrorCode =
  | 'internal_error'
  | 'configuration_error'
  | 'earth_engine_auth_error'
  | 'earth_engine_error'
  | 'no_imagery'
  | 'invalid_aoi'
  | 'invalid_request'
  // Client-side codes, never sent by the server:
  | 'network_error'
  | 'timeout'
  | 'aborted'
  | 'malformed_response'

/**
 * A failed API call, carrying the backend's machine-readable code.
 *
 * `details` is whatever the backend attached - for `no_imagery` it typically
 * includes the searched range and the cloud threshold used, which is exactly
 * what the UI needs to suggest "widen the dates or raise the cloud limit".
 */
export class ApiError extends Error {
  readonly code: ApiErrorCode | string
  readonly status: number
  readonly details: Record<string, unknown>

  constructor(
    code: ApiErrorCode | string,
    message: string,
    status = 0,
    details: Record<string, unknown> = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.details = details
  }

  /** True when the failure is plausibly transient and a retry may succeed. */
  get isRetryable(): boolean {
    return (
      this.code === 'earth_engine_error' ||
      this.code === 'network_error' ||
      this.code === 'timeout' ||
      this.code === 'internal_error'
    )
  }

  /** True when an operator has to configure something before this can work. */
  get isSetupProblem(): boolean {
    return this.code === 'earth_engine_auth_error' || this.code === 'configuration_error'
  }

  /** Remediation steps, when the backend supplied any. */
  get remediation(): string[] {
    const steps = this.details['remediation']
    if (!Array.isArray(steps)) return []
    return steps.filter((step): step is string => typeof step === 'string')
  }
}

interface RequestOptions {
  /** Lets a caller cancel in-flight work, e.g. when a component unmounts. */
  signal?: AbortSignal
  /** Overrides {@link REQUEST_TIMEOUT_MS} for this call. */
  timeoutMs?: number
}

function buildUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${normalized}`
}

/**
 * Extract an {@link ApiError} from a non-2xx response.
 *
 * FastAPI's own 422 for a schema violation is *not* in our envelope format - it
 * is `{detail: [...]}`. We handle both so a validation bug surfaces a readable
 * message instead of "Unknown error".
 */
async function toApiError(response: Response): Promise<ApiError> {
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    return new ApiError(
      'malformed_response',
      `Server returned ${response.status} with a non-JSON body.`,
      response.status,
    )
  }

  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>

    // CropSense envelope.
    if (typeof record['code'] === 'string' && typeof record['message'] === 'string') {
      const envelope = record as unknown as ErrorResponse
      return new ApiError(
        envelope.code,
        envelope.message,
        response.status,
        envelope.details ?? {},
      )
    }

    // FastAPI/pydantic request-validation shape.
    if (Array.isArray(record['detail'])) {
      const messages = record['detail']
        .map((item) => {
          if (!item || typeof item !== 'object') return null
          const entry = item as Record<string, unknown>
          const location = Array.isArray(entry['loc']) ? entry['loc'].join('.') : ''
          const message = typeof entry['msg'] === 'string' ? entry['msg'] : 'invalid value'
          return location ? `${location}: ${message}` : message
        })
        .filter((line): line is string => line !== null)
      return new ApiError(
        'invalid_request',
        messages.length > 0 ? messages.join('; ') : 'Request validation failed.',
        response.status,
        { detail: record['detail'] },
      )
    }

    if (typeof record['detail'] === 'string') {
      return new ApiError('invalid_request', record['detail'], response.status)
    }
  }

  return new ApiError(
    'malformed_response',
    `Server returned ${response.status} in an unrecognised format.`,
    response.status,
  )
}

/**
 * Issue a JSON request and return the parsed body.
 *
 * @throws {ApiError} for any non-2xx response, network failure or timeout.
 */
async function request<TResponse>(
  method: 'GET' | 'POST' | 'DELETE',
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<TResponse> {
  const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS
  const timeoutController = new AbortController()
  const timer = window.setTimeout(() => timeoutController.abort(), timeoutMs)

  // Combine the caller's signal with our timeout so either can cancel.
  const signals: AbortSignal[] = [timeoutController.signal]
  if (options.signal) signals.push(options.signal)
  const signal = signals.length > 1 ? AbortSignal.any(signals) : timeoutController.signal

  try {
    const response = await fetch(buildUrl(path), {
      method,
      headers: body === undefined ? { Accept: 'application/json' } : {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })

    if (!response.ok) {
      throw await toApiError(response)
    }

    if (response.status === 204) {
      return undefined as TResponse
    }

    try {
      return (await response.json()) as TResponse
    } catch {
      throw new ApiError('malformed_response', 'Server returned invalid JSON.', response.status)
    }
  } catch (error) {
    if (error instanceof ApiError) throw error

    // Distinguish "we timed out" from "the caller cancelled": one is a problem
    // worth showing, the other is normal navigation.
    if (timeoutController.signal.aborted) {
      throw new ApiError(
        'timeout',
        `Request timed out after ${Math.round(timeoutMs / 1000)}s. Earth Engine may be busy, ` +
          'or the area/date range may be too large.',
        0,
      )
    }
    if (options.signal?.aborted) {
      throw new ApiError('aborted', 'Request cancelled.', 0)
    }

    const detail = error instanceof Error ? error.message : String(error)
    throw new ApiError(
      'network_error',
      `Could not reach the CropSense API (${detail}). Is the backend running?`,
      0,
    )
  } finally {
    window.clearTimeout(timer)
  }
}

export function apiGet<TResponse>(path: string, options?: RequestOptions): Promise<TResponse> {
  return request<TResponse>('GET', path, undefined, options)
}

export function apiPost<TResponse>(
  path: string,
  body: unknown,
  options?: RequestOptions,
): Promise<TResponse> {
  return request<TResponse>('POST', path, body, options)
}

export function apiDelete<TResponse>(path: string, options?: RequestOptions): Promise<TResponse> {
  return request<TResponse>('DELETE', path, undefined, options)
}
