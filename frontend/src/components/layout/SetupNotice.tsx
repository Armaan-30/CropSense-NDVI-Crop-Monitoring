import { Callout } from '@/components/common/Callout'
import { formatCount, formatDuration } from '@/utils/format'
import type { ApiError } from '@/services/apiClient'
import type { AsyncTask } from '@/hooks/useAsyncTask'
import type { EarthEngineStatus, GEETestResponse } from '@/types/api'

interface SetupNoticeProps {
  status: EarthEngineStatus | null
  healthError: ApiError | null
  test: AsyncTask<[], GEETestResponse>
}

/**
 * Setup guidance shown when Earth Engine is not usable, plus a live test.
 *
 * The remediation steps are the backend's own - it knows which credential path
 * it looked for and what was missing, and repeating a guess here would drift out
 * of date. Nothing in this component pretends the connection works: with no
 * credentials, every analysis will fail, and saying so up front is more useful
 * than a generic error 30 seconds into the first request.
 */
export function SetupNotice({ status, healthError, test }: SetupNoticeProps) {
  const result = test.data

  if (healthError) {
    return (
      <Callout variant="warning" title="Cannot reach the backend">
        <p>{healthError.message}</p>
        <p>
          Start the API with <code>uvicorn app.main:app --reload</code> from the <code>backend</code>{' '}
          directory, then press Recheck.
        </p>
      </Callout>
    )
  }

  if (!status) return null

  return (
    <div className="stack">
      {status.initialized ? (
        <dl className="kv">
          <dt>Auth method</dt>
          <dd>{status.auth_method ?? '—'}</dd>
          <dt>Project</dt>
          <dd className="table__mono">{status.project ?? '—'}</dd>
          {status.service_account_email ? (
            <>
              <dt>Service account</dt>
              <dd className="table__mono">{status.service_account_email}</dd>
            </>
          ) : null}
          <dt>High-volume endpoint</dt>
          <dd>{status.high_volume_endpoint ? 'Yes' : 'No'}</dd>
          <dt>Verified round trip</dt>
          <dd>
            {status.reachable === null
              ? 'Not yet tested — initialisation succeeded, but no call has been made'
              : status.reachable
                ? 'Yes'
                : 'No'}
          </dd>
        </dl>
      ) : (
        <Callout variant="warning" title="Earth Engine is not configured">
          <p>
            {status.error ??
              'The backend started without Earth Engine credentials, so analysis requests will fail.'}
          </p>
          {status.remediation.length > 0 ? (
            <ol className="advice">
              {status.remediation.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          ) : null}
        </Callout>
      )}

      <button
        type="button"
        className="button button--secondary"
        onClick={() => void test.run()}
        disabled={test.isLoading}
      >
        {test.isLoading ? 'Testing…' : 'Run connection test'}
      </button>

      {test.error ? <p className="field__error">{test.error.message}</p> : null}

      {result ? (
        <Callout
          variant={result.success ? 'info' : 'warning'}
          title={result.success ? 'Connection test passed' : 'Connection test failed'}
        >
          <p>{result.message}</p>
          {result.success ? (
            <dl className="kv">
              <dt>Round trip</dt>
              <dd>{formatDuration(result.round_trip_ms)}</dd>
              <dt>Server-side value</dt>
              <dd>{result.server_side_number ?? '—'}</dd>
              <dt>Sample collection</dt>
              <dd className="table__mono">{result.sample_collection_id ?? '—'}</dd>
              <dt>Scenes visible</dt>
              <dd>{formatCount(result.sample_scene_count)}</dd>
              {result.sample_scene_id ? (
                <>
                  <dt>Example scene</dt>
                  <dd className="table__mono">{result.sample_scene_id}</dd>
                </>
              ) : null}
            </dl>
          ) : result.remediation.length > 0 ? (
            <ol className="advice">
              {result.remediation.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          ) : null}
        </Callout>
      ) : null}
    </div>
  )
}
