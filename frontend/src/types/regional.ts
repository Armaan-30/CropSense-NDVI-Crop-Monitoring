/** Shape of the non-sensitive JSON coverage report emitted by the pilot CLI. */
export interface RegionalFieldResult {
  field_id: string
  state: 'queued' | 'processing' | 'complete' | 'no_imagery' | 'failed'
  cultivated_area_ha: number
  scene_count: number | null
  mean_ndvi: number | null
  valid_pixel_fraction: number | null
  usable_area_ha: number | null
  warnings: string[]
  error: string | null
}

export interface RegionalCoverageReport {
  run_id: string
  state: string
  updated_at: string
  region: string
  season: string
  date_window: { start: string; end: string }
  dataset: {
    name: string
    release: string
    license: string
    authorization_reference: string
  }
  denominator: {
    cultivated_area_ha: number
    basis: 'net_sown' | 'gross_cropped' | 'other' | 'unspecified'
    source: string
    as_of: string
  }
  target: {
    fraction: number
    area_ha: number
    processed_area_ha: number
    attempted_area_ha: number
    cloud_valid_area_ha: number
    processed_percent: number
    cloud_valid_percent: number
    target_met: boolean
  }
  field_counts: Record<string, number>
  areas_by_state_ha: Record<string, number>
  fields: RegionalFieldResult[]
  accuracy: number | null
  accuracy_note: string
  report_file?: string
}
