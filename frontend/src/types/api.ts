/**
 * TypeScript mirrors of the CropSense backend schemas.
 *
 * These interfaces are hand-maintained against `backend/app/schemas/*.py`.
 * Field names use the backend's snake_case verbatim - renaming at the boundary
 * would mean a translation layer to keep in sync, and the payloads are read far
 * more often than they are written.
 *
 * `null` vs `undefined`: the backend emits JSON `null` for absent optional
 * values (pydantic `float | None`), so optional numbers are typed
 * `number | null` rather than `number | undefined`. Statistics legitimately
 * come back null when an AOI has no cloud-free pixels - that is a real result,
 * not an error, and the UI must render it as "no data" rather than 0.
 */

// ---------------------------------------------------------------------------
// GeoJSON (only the subset the backend accepts)
// ---------------------------------------------------------------------------

/** A `[longitude, latitude]` pair, in that order, per the GeoJSON spec. */
export type Position = [number, number]

export interface PointGeometry {
  type: 'Point'
  coordinates: Position
}

export interface PolygonGeometry {
  type: 'Polygon'
  /** Array of linear rings; ring[0] is the exterior ring, closed (first === last). */
  coordinates: Position[][]
}

export interface MultiPolygonGeometry {
  type: 'MultiPolygon'
  coordinates: Position[][][]
}

/** Geometry types accepted as an AOI by `POST /api/ndvi/*`. */
export type AOIGeometry = PointGeometry | PolygonGeometry | MultiPolygonGeometry

/** Server-computed description of the AOI actually analysed (after buffering). */
export interface AOISummary {
  geometry_type: string
  area_ha: number
  area_km2: number
  /** `[longitude, latitude]`. */
  centroid: number[]
  /** `[min_lon, min_lat, max_lon, max_lat]`. */
  bbox: number[]
}

// ---------------------------------------------------------------------------
// Enumerations (mirroring the backend StrEnums)
// ---------------------------------------------------------------------------

export type CloudMaskMethod = 'cs_plus' | 'scl' | 'qa60' | 'none'
export type CompositeMethod = 'median' | 'mean' | 'greenest' | 'most_recent'
export type TemporalAggregation = 'scene' | 'weekly' | 'biweekly' | 'monthly'

export const CLOUD_MASK_METHODS: readonly CloudMaskMethod[] = ['cs_plus', 'scl', 'qa60', 'none']
export const COMPOSITE_METHODS: readonly CompositeMethod[] = [
  'median',
  'mean',
  'greenest',
  'most_recent',
]
export const TEMPORAL_AGGREGATIONS: readonly TemporalAggregation[] = [
  'scene',
  'weekly',
  'biweekly',
  'monthly',
]

// ---------------------------------------------------------------------------
// Shared result shapes
// ---------------------------------------------------------------------------

/** An inclusive-start / inclusive-end window. Dates are ISO `YYYY-MM-DD`. */
export interface DateRange {
  start_date: string
  end_date: string
}

export interface LegendStop {
  label: string
  /** CSS hex colour. */
  color: string
  value_min: number | null
  value_max: number | null
}

/**
 * A ready-to-render Earth Engine raster layer.
 *
 * `tile_url_template` is a signed, short-lived Earth Engine tile endpoint. It
 * carries no service-account key, so it is safe in the browser - but it does
 * expire, so it must not be persisted across sessions.
 */
export interface MapLayer {
  id: string
  name: string
  description: string
  tile_url_template: string
  attribution: string
  opacity: number
  legend: LegendStop[]
  /** `[min, max]` of the stretched value range for continuous layers. */
  value_range: number[] | null
}

export interface NDVIStatistics {
  mean: number | null
  min: number | null
  max: number | null
  median: number | null
  std_dev: number | null
  p10: number | null
  p90: number | null
  valid_pixel_count: number | null
  total_pixel_count: number | null
  /** 0-1. Low values mean the statistics describe only a fraction of the AOI. */
  valid_pixel_fraction: number | null
  scale_m: number | null
}

export interface HealthClassStat {
  key: string
  label: string
  color: string
  /** Inclusive lower NDVI bound; `null` means unbounded (-1). */
  ndvi_min: number | null
  /** Exclusive upper NDVI bound; `null` means unbounded (+1). */
  ndvi_max: number | null
  area_ha: number
  /** Share of the cloud-free classified area, 0-100. */
  percent_of_valid: number
  pixel_count: number
}

export interface HealthSummary {
  /** The four class boundaries actually used for this request. */
  thresholds: number[]
  /** `'request'` when the client overrode them, otherwise `'server_default'`. */
  thresholds_source: string
  classes: HealthClassStat[]
  dominant_class: string | null
  classified_area_ha: number
  /** Mandatory caveat that thresholds are generic. Always render this. */
  calibration_note: string
}

/** Provenance of the imagery behind a result. Every number traces back here. */
export interface ImagerySummary {
  collection_id: string
  scene_count: number
  scene_dates: string[]
  scene_ids: string[]
  first_scene_date: string | null
  last_scene_date: string | null
  mean_scene_cloud_percent: number | null
  cloud_threshold_percent: number
  cloud_mask_method: CloudMaskMethod
  composite_method: CompositeMethod
  requested_range: DateRange
}

/** Uniform error envelope returned for every non-2xx response. */
export interface ErrorResponse {
  code: string
  message: string
  details: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Request shapes
// ---------------------------------------------------------------------------

/**
 * Per-request processing overrides. The backend rejects unknown keys
 * (`extra="forbid"`), so only send fields the user actually changed.
 */
export interface AnalysisOptions {
  cloud_mask_method?: CloudMaskMethod
  composite_method?: CompositeMethod
  /** Analysis scale in metres, 10-1000. */
  scale_m?: number
  /** Exactly four strictly ascending values in [-1, 1]. */
  ndvi_class_thresholds?: number[]
  /** Cloud Score+ `cs_cdf` cut-off, 0-1. Only used when method is `cs_plus`. */
  cloud_score_plus_threshold?: number
  include_true_color_layer?: boolean
}

interface BaseAnalysisRequest {
  aoi: AOIGeometry
  /** Outward buffer in metres, 0-20000. Also turns a Point into a circle. */
  buffer_m?: number
  /** Scene-level `CLOUDY_PIXEL_PERCENTAGE` cut-off, 0-100. */
  cloud_threshold?: number
  options?: AnalysisOptions
}

export interface NDVIAnalyzeRequest extends BaseAnalysisRequest {
  start_date: string
  end_date: string
}

export interface TimeSeriesRequest extends BaseAnalysisRequest {
  start_date: string
  end_date: string
  aggregation?: TemporalAggregation
  /** Drop time steps whose cloud-free coverage is below this fraction, 0-1. */
  min_valid_fraction?: number
}

export interface ChangeDetectionRequest extends BaseAnalysisRequest {
  baseline_start_date: string
  baseline_end_date: string
  recent_start_date: string
  recent_end_date: string
  /** NDVI drop (positive number) that counts as a decline. */
  decline_threshold?: number
}

// ---------------------------------------------------------------------------
// Response shapes
// ---------------------------------------------------------------------------

export interface NDVIAnalyzeResponse {
  aoi: AOISummary
  imagery: ImagerySummary
  statistics: NDVIStatistics
  health: HealthSummary
  layers: MapLayer[]
  warnings: string[]
  notes: string[]
  computed_at: string
  duration_ms: number
}

export interface TimeSeriesPoint {
  /** ISO date of the time step (scene date, or period start when aggregated). */
  date: string
  mean_ndvi: number | null
  min_ndvi: number | null
  max_ndvi: number | null
  median_ndvi: number | null
  std_dev_ndvi: number | null
  valid_pixel_fraction: number | null
  scene_count: number
  scene_cloud_percent: number | null
  scene_id: string | null
}

export interface TrendSummary {
  n_points: number
  slope_ndvi_per_day: number | null
  slope_ndvi_per_30_days: number | null
  intercept: number | null
  /** Coefficient of determination of the linear fit, 0-1. */
  r_squared: number | null
  direction: string
  first_value: number | null
  last_value: number | null
  absolute_change: number | null
  interpretation: string
}

export interface TimeSeriesResponse {
  aoi: AOISummary
  collection_id: string
  requested_range: DateRange
  aggregation: TemporalAggregation
  cloud_threshold_percent: number
  cloud_mask_method: CloudMaskMethod
  scale_m: number
  points: TimeSeriesPoint[]
  /** Time steps dropped for insufficient cloud-free coverage. */
  excluded_point_count: number
  trend: TrendSummary | null
  warnings: string[]
  notes: string[]
  computed_at: string
  duration_ms: number
}

export interface ChangeStatistics {
  mean_change: number | null
  min_change: number | null
  max_change: number | null
  median_change: number | null
  std_dev_change: number | null
  /** Area where BOTH periods have cloud-free data - the only comparable area. */
  comparable_area_ha: number | null
  comparable_area_fraction: number | null
  declined_area_ha: number | null
  declined_percent_of_comparable: number | null
  improved_area_ha: number | null
  improved_percent_of_comparable: number | null
  decline_threshold: number
}

export interface ChangeDetectionResponse {
  aoi: AOISummary
  baseline_imagery: ImagerySummary
  recent_imagery: ImagerySummary
  baseline_statistics: NDVIStatistics
  recent_statistics: NDVIStatistics
  baseline_health: HealthSummary
  recent_health: HealthSummary
  change: ChangeStatistics
  layers: MapLayer[]
  warnings: string[]
  notes: string[]
  computed_at: string
  duration_ms: number
}

// ---------------------------------------------------------------------------
// System endpoints
// ---------------------------------------------------------------------------

export interface EarthEngineStatus {
  initialized: boolean
  /** True only after a real round trip. `null` when never tested. */
  reachable: boolean | null
  auth_method: string | null
  project: string | null
  service_account_email: string | null
  high_volume_endpoint: boolean | null
  error: string | null
  remediation: string[]
}

export interface HealthResponse {
  /** `'ok'` or `'degraded'`. HTTP status is 200 either way - read this field. */
  status: string
  app_name: string
  version: string
  environment: string
  earth_engine: EarthEngineStatus
  timestamp: string
}

/** One entry of `ConfigResponse.health_classes`. */
export interface HealthClassDefinition {
  key: string
  label: string
  color: string
  code: number
  description: string
}

export interface ConfigResponse {
  collection_id: string
  band_red: string
  band_nir: string
  default_cloud_mask_method: CloudMaskMethod
  default_composite_method: CompositeMethod
  default_scale_m: number
  default_ndvi_class_thresholds: number[]
  default_decline_threshold: number
  health_classes: HealthClassDefinition[]
  ndvi_palette: string[]
  max_aoi_area_km2: number
  max_date_range_days: number
  calibration_note: string
  limitations: string[]
}

export interface GEETestResponse {
  success: boolean
  auth_method: string | null
  project: string | null
  round_trip_ms: number | null
  server_side_number: number | null
  sample_collection_id: string | null
  sample_scene_count: number | null
  sample_scene_id: string | null
  message: string
  remediation: string[]
}
