import { formatTimestamp } from '@/utils/format'
import type { ApiError } from '@/services/apiClient'
import type { HealthResponse } from '@/types/api'

interface AppHeaderProps {
  health: HealthResponse | null
  healthError: ApiError | null
  isRefreshing: boolean
  onRefresh: () => void
}

type PillTone = 'ok' | 'warn' | 'bad' | 'idle'

function statusPill(
  health: HealthResponse | null,
  healthError: ApiError | null,
  isRefreshing: boolean,
): { tone: PillTone; label: string; detail: string } {
  if (isRefreshing && !health) {
    return { tone: 'idle', label: 'Checking backend…', detail: '' }
  }
  if (healthError) {
    return {
      tone: 'bad',
      label: 'Backend unreachable',
      detail: healthError.message,
    }
  }
  if (!health) {
    return { tone: 'idle', label: 'Backend status unknown', detail: '' }
  }
  if (health.earth_engine.initialized) {
    return {
      tone: 'ok',
      label: 'Earth Engine ready',
      detail: [health.earth_engine.auth_method, health.earth_engine.project]
        .filter((value): value is string => Boolean(value))
        .join(' · '),
    }
  }
  return {
    tone: 'warn',
    label: 'Earth Engine not configured',
    detail: health.earth_engine.error ?? 'No credentials were found.',
  }
}

/** Application header with the backend / Earth Engine readiness pill. */
export function AppHeader({ health, healthError, isRefreshing, onRefresh }: AppHeaderProps) {
  const pill = statusPill(health, healthError, isRefreshing)

  return (
    <header className="app-header">
      <div className="app-header__brand">
        <h1 className="app-header__title">CropSense</h1>
        <p className="app-header__tagline">
          Satellite NDVI monitoring · Sentinel-2 Surface Reflectance via Google Earth Engine
        </p>
      </div>

      <div className="app-header__status">
        <span className={`pill pill--${pill.tone}`}>
          <span className="pill__dot" aria-hidden="true" />
          {pill.label}
        </span>
        {pill.detail ? <span className="app-header__detail">{pill.detail}</span> : null}
        {health ? (
          <span className="app-header__detail">
            v{health.version} · {health.environment} · checked {formatTimestamp(health.timestamp)}
          </span>
        ) : null}
        <button
          type="button"
          className="button button--ghost"
          onClick={onRefresh}
          disabled={isRefreshing}
        >
          {isRefreshing ? 'Checking…' : 'Recheck'}
        </button>
      </div>
    </header>
  )
}
