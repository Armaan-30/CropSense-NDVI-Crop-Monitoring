import { expect, test } from '@playwright/test'

const testAOI = {
  type: 'Polygon',
  coordinates: [
    [
      [75.55, 21.0],
      [75.551, 21.0],
      [75.551, 21.001],
      [75.55, 21.001],
      [75.55, 21.0],
    ],
  ],
}

const healthClasses = [
  { key: 'very_low', label: 'Very low', color: '#8c510a', code: 1, description: 'Lowest class' },
  { key: 'low', label: 'Low', color: '#d8b365', code: 2, description: 'Low class' },
  { key: 'moderate', label: 'Moderate', color: '#f6e8c3', code: 3, description: 'Middle class' },
  { key: 'healthy', label: 'Healthy', color: '#5ab4ac', code: 4, description: 'Healthy class' },
  { key: 'very_healthy', label: 'Very healthy', color: '#01665e', code: 5, description: 'Highest class' },
]

const mockAnalysis = {
  aoi: {
    geometry_type: 'Polygon',
    area_ha: 1.0,
    area_km2: 0.01,
    centroid: [75.5505, 21.0005],
    bbox: [75.55, 21, 75.551, 21.001],
  },
  imagery: {
    collection_id: 'COPERNICUS/S2_SR_HARMONIZED',
    scene_count: 2,
    scene_dates: ['2026-09-10', '2026-09-20'],
    scene_ids: ['test-scene-1', 'test-scene-2'],
    first_scene_date: '2026-09-10',
    last_scene_date: '2026-09-20',
    mean_scene_cloud_percent: 8,
    cloud_threshold_percent: 30,
    cloud_mask_method: 'scl',
    composite_method: 'median',
    requested_range: { start_date: '2026-09-01', end_date: '2026-09-30' },
  },
  statistics: {
    mean: 0.642,
    min: 0.31,
    max: 0.81,
    median: 0.65,
    std_dev: 0.08,
    p10: 0.51,
    p90: 0.74,
    valid_pixel_count: 900,
    total_pixel_count: 1000,
    valid_pixel_fraction: 0.9,
    scale_m: 20,
  },
  health: {
    thresholds: [0.2, 0.4, 0.6, 0.8],
    thresholds_source: 'server_default',
    classes: healthClasses.map((entry, index) => ({
      ...entry,
      ndvi_min: index ? [null, 0.2, 0.4, 0.6, 0.8][index] : null,
      ndvi_max: index < 4 ? [0.2, 0.4, 0.6, 0.8, null][index] : null,
      area_ha: index === 3 ? 0.9 : 0.025,
      percent_of_valid: index === 3 ? 80 : 5,
      pixel_count: index === 3 ? 720 : 45,
    })),
    dominant_class: 'healthy',
    classified_area_ha: 1,
    calibration_note: 'Test fixture only. These classes are not crop-validated.',
  },
  layers: [],
  warnings: [],
  notes: ['Browser test fixture; no satellite analysis was run.'],
  computed_at: '2026-10-11T00:00:00Z',
  duration_ms: 42,
}

const mockRegionalReport = {
  run_id: 'test-run-001',
  state: 'paused',
  updated_at: '2026-10-11T00:00:00Z',
  region: 'Jalgaon pilot',
  season: 'kharif-2026',
  date_window: { start: '2026-09-01', end: '2026-09-30' },
  dataset: {
    name: 'test authorized source',
    release: 'test-v1',
    license: 'test permission',
    authorization_reference: 'test-approval',
  },
  denominator: {
    cultivated_area_ha: 100,
    basis: 'net_sown',
    source: 'test official area record',
    as_of: '2026-10-01',
  },
  target: {
    fraction: 0.5,
    area_ha: 50,
    processed_area_ha: 25,
    attempted_area_ha: 30,
    cloud_valid_area_ha: 20,
    processed_percent: 25,
    cloud_valid_percent: 20,
    target_met: false,
  },
  field_counts: { complete: 1, no_imagery: 0, failed: 1, queued: 3 },
  areas_by_state_ha: { complete: 25, no_imagery: 0, failed: 5, queued: 70 },
  fields: [
    {
      field_id: 'pseudonymous-field-1',
      state: 'complete',
      cultivated_area_ha: 25,
      scene_count: 2,
      mean_ndvi: 0.42,
      valid_pixel_fraction: 0.8,
      usable_area_ha: 20,
      warnings: [],
      error: null,
    },
  ],
  accuracy: null,
  accuracy_note: 'Test report only. Accuracy requires independent observations.',
  report_file: 'test-report.json',
}

test.beforeEach(async ({ page }) => {
  await page.route('**/health', (route) =>
    route.fulfill({
      json: {
        status: 'ok',
        app_name: 'CropSense API',
        version: 'test',
        environment: 'test',
        earth_engine: {
          initialized: true,
          reachable: true,
          auth_method: 'test_stub',
          project: 'test-project',
          service_account_email: null,
          high_volume_endpoint: true,
          error: null,
          remediation: [],
        },
        timestamp: '2026-10-11T00:00:00Z',
      },
    }),
  )
  await page.route('**/api/system/config', (route) =>
    route.fulfill({
      json: {
        collection_id: 'COPERNICUS/S2_SR_HARMONIZED',
        band_red: 'B4',
        band_nir: 'B8',
        default_cloud_mask_method: 'cs_plus',
        default_composite_method: 'median',
        default_scale_m: 10,
        default_ndvi_class_thresholds: [0.2, 0.4, 0.6, 0.8],
        default_decline_threshold: 0.15,
        health_classes: healthClasses,
        ndvi_palette: ['#8c510a', '#d8b365', '#f6e8c3', '#5ab4ac', '#01665e'],
        max_aoi_area_km2: 2500,
        max_date_range_days: 730,
        calibration_note: 'Test configuration only; calibrate with field data.',
        limitations: ['NDVI does not diagnose disease.'],
      },
    }),
  )
  await page.route('**/api/history**', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/ndvi/analyze', async (route) => {
    const body = route.request().postDataJSON()
    expect(body.aoi.type).toBe('Polygon')
    expect(body.options.scale_m).toBeDefined()
    await route.fulfill({ json: mockAnalysis })
  })
})

test('field selection reaches analysis and renders the response', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'CropSense' })).toBeVisible()
  await expect(page.getByText('Earth Engine ready')).toBeVisible()

  await page.getByRole('button', { name: 'Paste GeoJSON' }).click()
  await page.getByLabel('GeoJSON').fill(JSON.stringify(testAOI))
  await page.getByRole('button', { name: 'Use this geometry' }).click()
  await expect(page.getByText(/Polygon · 5 vertices/)).toBeVisible()

  await page.getByRole('button', { name: 'Compute NDVI' }).click()
  await expect(page.getByText('Mean NDVI', { exact: true })).toBeVisible()
  await expect(page.getByText('0.642')).toBeVisible()
  await expect(page.getByText('COPERNICUS/S2_SR_HARMONIZED')).toBeVisible()
  await expect(page.getByText('Browser test fixture; no satellite analysis was run.')).toBeVisible()
})

test('Maharashtra demo area is clearly labeled and reaches the analysis endpoint', async ({ page }) => {
  let submittedGeometry: unknown
  await page.route('**/api/ndvi/analyze', async (route) => {
    submittedGeometry = route.request().postDataJSON().aoi
    await route.fulfill({ json: mockAnalysis })
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Load demo area near Jalgaon, Maharashtra' }).click()
  await expect(page.getByText(/demo is a small rectangle.*not a surveyed farm boundary/i)).toBeVisible()
  await page.getByRole('button', { name: 'Compute NDVI' }).click()
  await expect(page.getByText('Mean NDVI', { exact: true })).toBeVisible()
  expect(submittedGeometry).toEqual({
    type: 'Polygon',
    coordinates: [[[75.55, 21], [75.551, 21], [75.551, 21.001], [75.55, 21.001], [75.55, 21]]],
  })
})

test('analysis modes switch without losing the selected field', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Paste GeoJSON' }).click()
  await page.getByLabel('GeoJSON').fill(JSON.stringify(testAOI))
  await page.getByRole('button', { name: 'Use this geometry' }).click()
  await page.getByRole('tab', { name: /Time series/ }).click()
  await expect(page.getByText(/Polygon · 5 vertices/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Build time series' })).toBeVisible()
})

test('regional dashboard displays processed and cloud-valid hectare coverage', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Coverage report JSON').setInputFiles({
    name: 'regional-report.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(mockRegionalReport)),
  })

  await expect(page.getByText('Jalgaon pilot · kharif-2026')).toBeVisible()
  await expect(page.getByText('25.00 ha · 25.0%')).toBeVisible()
  await expect(page.getByText('20.00 ha · 20.0%')).toBeVisible()
  await expect(page.getByText('Accuracy not measured')).toBeVisible()
  await expect(page.getByText('pseudonymous-field-1')).toBeVisible()
})
