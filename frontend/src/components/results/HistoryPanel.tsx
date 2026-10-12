import { useCallback, useEffect, useState } from 'react'
import { Callout } from '@/components/common/Callout'
import { EmptyState } from '@/components/common/EmptyState'
import { Panel } from '@/components/common/Panel'
import { deleteHistory, fetchHistory } from '@/services/historyApi'
import { formatArea, formatNDVI, formatTimestamp } from '@/utils/format'
import type { HistorySummary } from '@/types/history'

interface HistoryPanelProps {
  refreshKey: string
}

const MODE_LABEL: Record<HistorySummary['mode'], string> = {
  snapshot: 'NDVI snapshot',
  series: 'Time series',
  compare: 'Period comparison',
}

export function HistoryPanel({ refreshKey }: HistoryPanelProps) {
  const [items, setItems] = useState<HistorySummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async (signal?: AbortSignal) => {
    setLoading(true)
    try {
      setItems(await fetchHistory(signal))
      setError(null)
    } catch (cause) {
      if (cause instanceof Error && cause.name === 'AbortError') return
      setError(cause instanceof Error ? cause.message : 'Could not load local history.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    queueMicrotask(() => {
      if (!controller.signal.aborted) void refresh(controller.signal)
    })
    return () => controller.abort()
  }, [refresh, refreshKey])

  const remove = async (id: string) => {
    setBusyId(id)
    try {
      await deleteHistory(id)
      setItems((current) => current.filter((item) => item.id !== id))
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not delete this entry.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <Panel
      title="Local analysis history"
      subtitle="Saved on this machine; signed map tiles are not retained."
      actions={
        <button type="button" className="button button--ghost" onClick={() => void refresh()} disabled={loading}>
          Refresh
        </button>
      }
    >
      {error ? <Callout variant="warning" title="History storage unavailable">{error}</Callout> : null}
      {loading && items.length === 0 ? <p className="hint">Loading saved analyses…</p> : null}
      {!loading && items.length === 0 && !error ? <EmptyState title="No saved analyses yet">Completed analyses will appear here.</EmptyState> : null}
      {items.length > 0 ? (
        <ul className="history-list">
          {items.map((item) => (
            <li className="history-item" key={item.id}>
              <div>
                <strong>{MODE_LABEL[item.mode]}</strong>
                <div className="hint">{formatTimestamp(item.created_at)}</div>
                <div className="history-item__meta">
                  {item.start_date ?? 'Period'} – {item.end_date ?? 'unknown'}
                  {item.area_ha !== null ? ` · ${formatArea(item.area_ha * 10_000)}` : ''}
                  {item.mean_ndvi !== null ? ` · mean NDVI ${formatNDVI(item.mean_ndvi)}` : ''}
                  {item.scene_count !== null ? ` · ${item.scene_count} scenes` : ''}
                </div>
              </div>
              <button type="button" className="button button--ghost" onClick={() => void remove(item.id)} disabled={busyId === item.id}>
                {busyId === item.id ? 'Deleting…' : 'Delete'}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </Panel>
  )
}
