import type { RegionalCoverageReport, RegionalFieldResult } from '@/types/regional'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || isFiniteNumber(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((entry) => typeof entry === 'string')
}

function isFieldResult(value: unknown): value is RegionalFieldResult {
  if (!isRecord(value)) return false
  return (
    typeof value.field_id === 'string' &&
    ['queued', 'processing', 'complete', 'no_imagery', 'failed'].includes(String(value.state)) &&
    isFiniteNumber(value.cultivated_area_ha) &&
    isNullableNumber(value.scene_count) &&
    isNullableNumber(value.mean_ndvi) &&
    isNullableNumber(value.valid_pixel_fraction) &&
    isNullableNumber(value.usable_area_ha) &&
    isStringArray(value.warnings) &&
    (typeof value.error === 'string' || value.error === null)
  )
}

/** Validate report JSON before rendering a local file selected by the user. */
export function parseRegionalCoverageReport(input: unknown): RegionalCoverageReport | null {
  if (!isRecord(input) || !isRecord(input.date_window)) return null
  if (!isRecord(input.dataset) || !isRecord(input.denominator) || !isRecord(input.target)) return null
  if (!isRecord(input.field_counts) || !isRecord(input.areas_by_state_ha)) return null
  if (!Array.isArray(input.fields) || !input.fields.every(isFieldResult)) return null
  if (
    typeof input.run_id !== 'string' ||
    typeof input.state !== 'string' ||
    typeof input.updated_at !== 'string' ||
    typeof input.region !== 'string' ||
    typeof input.season !== 'string' ||
    typeof input.date_window.start !== 'string' ||
    typeof input.date_window.end !== 'string' ||
    typeof input.dataset.name !== 'string' ||
    typeof input.dataset.release !== 'string' ||
    typeof input.dataset.license !== 'string' ||
    typeof input.dataset.authorization_reference !== 'string' ||
    !isFiniteNumber(input.denominator.cultivated_area_ha) ||
    !['net_sown', 'gross_cropped', 'other', 'unspecified'].includes(
      String(input.denominator.basis),
    ) ||
    typeof input.denominator.source !== 'string' ||
    typeof input.denominator.as_of !== 'string' ||
    !isFiniteNumber(input.target.fraction) ||
    !isFiniteNumber(input.target.area_ha) ||
    !isFiniteNumber(input.target.processed_area_ha) ||
    !isFiniteNumber(input.target.attempted_area_ha) ||
    !isFiniteNumber(input.target.cloud_valid_area_ha) ||
    !isFiniteNumber(input.target.processed_percent) ||
    !isFiniteNumber(input.target.cloud_valid_percent) ||
    typeof input.target.target_met !== 'boolean' ||
    !Object.values(input.field_counts).every(isFiniteNumber) ||
    !Object.values(input.areas_by_state_ha).every(isFiniteNumber) ||
    (input.accuracy !== null && !isFiniteNumber(input.accuracy)) ||
    typeof input.accuracy_note !== 'string'
  ) {
    return null
  }
  return input as unknown as RegionalCoverageReport
}
