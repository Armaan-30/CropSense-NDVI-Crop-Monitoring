interface LoadingStateProps {
  /** What is being computed, e.g. "Computing NDVI composite". */
  message?: string
  /** Elapsed milliseconds from `useAsyncTask`, shown once it gets slow. */
  elapsedMs?: number
  onCancel?: () => void
}

/**
 * Loading indicator sized for Earth Engine latency.
 *
 * A snapshot over a small field usually returns in a few seconds, but a long
 * date range or a large AOI genuinely takes 30-60 seconds. After 8 seconds we
 * start showing the elapsed time and an explanation, so a slow-but-working
 * request does not read as a hung page.
 */
export function LoadingState({ message = 'Working…', elapsedMs = 0, onCancel }: LoadingStateProps) {
  const seconds = Math.floor(elapsedMs / 1000)
  const isSlow = seconds >= 8

  return (
    <div className="state state--loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <div className="state__text">
        <p className="state__title">
          {message}
          {seconds > 0 ? ` (${seconds}s)` : ''}
        </p>
        {isSlow ? (
          <p className="state__detail">
            Earth Engine is computing this on demand. Large areas, long date ranges and fine
            analysis scales all take longer.
          </p>
        ) : null}
      </div>
      {onCancel ? (
        <button type="button" className="button button--ghost" onClick={onCancel}>
          Cancel
        </button>
      ) : null}
    </div>
  )
}
