export interface HistorySummary {
  id: string
  mode: 'snapshot' | 'series' | 'compare'
  created_at: string
  start_date: string | null
  end_date: string | null
  area_ha: number | null
  mean_ndvi: number | null
  scene_count: number | null
}

export interface HistoryDetail extends HistorySummary {
  request: Record<string, unknown>
  result: Record<string, unknown>
}
