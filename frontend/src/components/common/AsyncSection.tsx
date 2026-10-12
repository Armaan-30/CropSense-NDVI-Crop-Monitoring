import type { ReactNode } from 'react'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import type { AsyncTaskState } from '@/hooks/useAsyncTask'

interface AsyncSectionProps<TData> {
  state: AsyncTaskState<TData>
  onRetry?: () => void
  onCancel?: () => void
  loadingMessage?: string
  /** Shown before the first run, and when a run returned nothing. */
  empty: ReactNode
  /** Extra, context-specific advice appended to the error state. */
  errorAdvice?: ReactNode
  children: (data: TData) => ReactNode
}

/**
 * Renders the four states of one async request: loading, failed, loaded, idle.
 *
 * Loading takes precedence over stale data on purpose. These requests take tens
 * of seconds, and leaving the previous field's numbers on screen while a new
 * field computes is the kind of thing that gets acted on by mistake.
 */
export function AsyncSection<TData>({
  state,
  onRetry,
  onCancel,
  loadingMessage,
  empty,
  errorAdvice,
  children,
}: AsyncSectionProps<TData>) {
  if (state.isLoading) {
    return (
      <LoadingState
        message={loadingMessage ?? 'Asking Earth Engine…'}
        elapsedMs={state.elapsedMs}
        onCancel={onCancel}
      />
    )
  }

  if (state.error) {
    return (
      <ErrorState error={state.error} onRetry={onRetry}>
        {errorAdvice}
      </ErrorState>
    )
  }

  if (state.data) {
    return <>{children(state.data)}</>
  }

  return <>{empty}</>
}
