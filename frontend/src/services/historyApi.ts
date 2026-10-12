import { apiDelete, apiGet } from '@/services/apiClient'
import type { HistorySummary } from '@/types/history'

export function fetchHistory(signal?: AbortSignal): Promise<HistorySummary[]> {
  return apiGet<HistorySummary[]>('/api/history?limit=20', { signal, timeoutMs: 15_000 })
}

export function deleteHistory(id: string, signal?: AbortSignal): Promise<void> {
  return apiDelete<void>(`/api/history/${encodeURIComponent(id)}`, { signal, timeoutMs: 15_000 })
}
