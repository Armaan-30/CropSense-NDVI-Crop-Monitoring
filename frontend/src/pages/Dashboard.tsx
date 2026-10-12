/**
 * The CropSense dashboard.
 *
 * This module is deliberately only wiring: state, validation and layout. Every
 * control and every result view is its own component, so a new analysis mode
 * means a new tab plus a new results component, not an edit to a monolith.
 *
 * Results are held per mode (`snapshot`, `series`, `compare`) rather than in one
 * slot. Earth Engine calls take tens of seconds, and switching tabs to check the
 * time series must not throw away a snapshot that just finished computing.
 */

import { useCallback, useMemo, useState } from 'react'
import { AppHeader } from '@/components/layout/AppHeader'
import { LimitationsPanel } from '@/components/layout/LimitationsPanel'
import { SetupNotice } from '@/components/layout/SetupNotice'
import { AsyncSection } from '@/components/common/AsyncSection'
import { Callout } from '@/components/common/Callout'
import { EmptyState } from '@/components/common/EmptyState'
import { Panel } from '@/components/common/Panel'
import { AOIPanel } from '@/components/controls/AOIPanel'
import { AnalysisOptionsForm } from '@/components/controls/AnalysisOptionsForm'
import { ChangeOptionsForm } from '@/components/controls/ChangeOptionsForm'
import { CloudFilterSlider } from '@/components/controls/CloudFilterSlider'
import { DateRangeField } from '@/components/controls/DateRangeField'
import { ModeTabs } from '@/components/controls/ModeTabs'
import { SeriesOptionsForm } from '@/components/controls/SeriesOptionsForm'
import { ThresholdEditor } from '@/components/controls/ThresholdEditor'
import { LayerSwitcher } from '@/components/map/LayerSwitcher'
import { MapView } from '@/components/map/MapView'
import { CompareResults } from '@/components/results/CompareResults'
import { SeriesResults } from '@/components/results/SeriesResults'
import { SnapshotResults } from '@/components/results/SnapshotResults'
import { HistoryPanel } from '@/components/results/HistoryPanel'
import { RegionalCoveragePanel } from '@/components/results/RegionalCoveragePanel'
import { useNDVIAnalysis, useTimeSeries, useChangeDetection } from '@/hooks/useAnalysis'
import { useEarthEngineTest, useHealthStatus, useServerConfig } from '@/hooks/useServerConfig'
import {
  buildAnalyzeRequest,
  buildChangeRequest,
  buildTimeSeriesRequest,
} from '@/services/requestBuilders'
import { daysBetween, earliestDateFor, isOrderedRange } from '@/utils/dates'
import { geometryBBox } from '@/utils/geometry'
import { defaultRanges, effectiveSettings } from '@/types/settings'
import type { AnalysisSettings, SettingsOverrides } from '@/types/settings'
import type { AnalysisMode } from '@/types/ui'
import type { AOIGeometry, DateRange, MapLayer } from '@/types/api'

/** Preferred initial raster per mode, by layer id. */
const PREFERRED_LAYERS: Record<AnalysisMode, string[]> = {
  snapshot: ['ndvi', 'health'],
  series: [],
  compare: ['ndvi_change', 'potential_stress', 'ndvi_recent'],
}

interface ModeRanges {
  snapshot: DateRange
  series: DateRange
  baseline: DateRange
  recent: DateRange
}

/** Validate a window the same way the backend will, to avoid a wasted round trip. */
function rangeProblem(range: DateRange, maxDays: number | null, label: string): string | null {
  if (!isOrderedRange(range.start_date, range.end_date)) {
    return `${label}: the end date is before the start date.`
  }
  if (maxDays !== null && daysBetween(range.start_date, range.end_date) > maxDays) {
    return `${label}: the window is longer than the server limit of ${maxDays} days.`
  }
  return null
}

export function Dashboard() {
  const config = useServerConfig()
  const health = useHealthStatus()
  const geeTest = useEarthEngineTest()

  const snapshot = useNDVIAnalysis()
  const series = useTimeSeries()
  const compare = useChangeDetection()

  const [mode, setMode] = useState<AnalysisMode>('snapshot')
  const [aoi, setAOI] = useState<AOIGeometry | null>(null)
  const [drawError, setDrawError] = useState<string | null>(null)
  const [overrides, setOverrides] = useState<SettingsOverrides>({})
  const [ranges, setRanges] = useState<ModeRanges>(defaultRanges)
  const [selectedLayerId, setSelectedLayerId] = useState<string | null>(null)
  const [layerOpacity, setLayerOpacity] = useState(1)
  const [fitBBox, setFitBBox] = useState<number[] | null>(null)
  const historyRefreshKey = [
    snapshot.data?.computed_at ?? '',
    series.data?.computed_at ?? '',
    compare.data?.computed_at ?? '',
  ].join('|')

  const configData = config.data

  // Derived, not synchronised: the server's defaults with the user's edits on
  // top. Nothing has to react to the config arriving.
  const settings = useMemo(() => effectiveSettings(configData, overrides), [configData, overrides])

  const layers = useMemo<MapLayer[]>(() => {
    if (mode === 'snapshot') return snapshot.data?.layers ?? []
    if (mode === 'compare') return compare.data?.layers ?? []
    return []
  }, [mode, snapshot.data, compare.data])

  /**
   * The layer actually displayed.
   *
   * `selectedLayerId` is the user's choice and is allowed to go stale - a
   * comparison's `ndvi_change` is not present in a snapshot's layer list. Rather
   * than correcting the stored value in an effect, the valid id is derived here
   * and a stale selection simply falls through to the mode's preferred layer.
   */
  const activeLayerId = useMemo<string | null>(() => {
    if (layers.length === 0) return null
    if (selectedLayerId !== null && layers.some((layer) => layer.id === selectedLayerId)) {
      return selectedLayerId
    }
    for (const preferred of PREFERRED_LAYERS[mode]) {
      if (layers.some((layer) => layer.id === preferred)) return preferred
    }
    return layers.find((layer) => layer.id !== 'true_color')?.id ?? null
  }, [layers, mode, selectedLayerId])

  const patchSettings = useCallback((patch: Partial<AnalysisSettings>) => {
    setOverrides((previous) => ({ ...previous, ...patch }))
  }, [])

  /** Apply a threshold edit, or drop the override entirely on a reset. */
  const changeThresholds = useCallback((thresholds: number[], isCustom: boolean) => {
    setOverrides((previous) => {
      if (isCustom) return { ...previous, thresholds, thresholdsAreCustom: true }
      const next = { ...previous }
      delete next.thresholds
      delete next.thresholdsAreCustom
      return next
    })
  }, [])

  const handleMapAOI = useCallback((geometry: AOIGeometry | null) => {
    setDrawError(null)
    setAOI(geometry)
  }, [])

  // A geometry that arrived by paste is off screen until we move the map to it.
  const handlePanelAOI = useCallback((geometry: AOIGeometry | null) => {
    setDrawError(null)
    setAOI(geometry)
    setFitBBox(geometry ? geometryBBox(geometry) : null)
  }, [])

  const maxDays = configData?.max_date_range_days ?? null
  const earliest = earliestDateFor(settings.cloudMaskMethod)

  const pointWithoutBuffer = aoi?.type === 'Point' && settings.bufferM <= 0
  const rangeIssue =
    mode === 'snapshot'
      ? rangeProblem(ranges.snapshot, maxDays, 'Date range')
      : mode === 'series'
        ? rangeProblem(ranges.series, maxDays, 'Series range')
        : (rangeProblem(ranges.baseline, maxDays, 'Baseline') ??
          rangeProblem(ranges.recent, maxDays, 'Recent period'))

  const blockingReason = !aoi
    ? 'Draw or paste a field boundary first.'
    : pointWithoutBuffer
      ? 'A marker has no area. Set an AOI buffer greater than 0 m in Processing options.'
      : rangeIssue

  const activeTask = mode === 'snapshot' ? snapshot : mode === 'series' ? series : compare

  const runActive = useCallback(async () => {
    if (!aoi || blockingReason) return
    if (mode === 'snapshot') {
      const result = await snapshot.run(buildAnalyzeRequest(aoi, ranges.snapshot, settings))
      if (result) setFitBBox(result.aoi.bbox)
      return
    }
    if (mode === 'series') {
      const result = await series.run(buildTimeSeriesRequest(aoi, ranges.series, settings))
      if (result) setFitBBox(result.aoi.bbox)
      return
    }
    const result = await compare.run(
      buildChangeRequest(aoi, ranges.baseline, ranges.recent, settings),
    )
    if (result) setFitBBox(result.aoi.bbox)
  }, [aoi, blockingReason, mode, ranges, settings, snapshot, series, compare])

  const classLabels = useMemo(
    () => (configData?.health_classes ?? []).map((entry) => entry.label),
    [configData],
  )

  const summaryAOI =
    mode === 'snapshot'
      ? (snapshot.data?.aoi ?? null)
      : mode === 'series'
        ? (series.data?.aoi ?? null)
        : (compare.data?.aoi ?? null)

  const snapshotStatistics = snapshot.data?.statistics ?? null

  return (
    <div className="app">
      <AppHeader
        health={health.data}
        healthError={health.error}
        isRefreshing={health.isLoading}
        onRefresh={() => void health.run()}
      />

      {config.error ? (
        <Callout variant="warning" title="Could not load the server configuration">
          {config.error.message} Defaults are being used for thresholds and limits, and they may not
          match the backend.
        </Callout>
      ) : null}

      <div className="layout">
        <aside className="sidebar">
          <Panel title="Field" subtitle="One area of interest at a time">
            <AOIPanel
              aoi={aoi}
              bufferM={settings.bufferM}
              onChange={handlePanelAOI}
              maxAreaKm2={configData?.max_aoi_area_km2 ?? null}
              summary={summaryAOI}
              drawError={drawError}
            />
          </Panel>

          <Panel title="Dates" subtitle="Sentinel-2 revisits every 5 days at best">
            <div className="stack">
              {mode === 'snapshot' ? (
                <DateRangeField
                  label="Analysis window"
                  value={ranges.snapshot}
                  onChange={(range) => setRanges((previous) => ({ ...previous, snapshot: range }))}
                  min={earliest}
                  maxDays={maxDays ?? undefined}
                  presets={[14, 30, 60, 90]}
                  hint="All cloud-free scenes in this window are composited into one image."
                />
              ) : null}

              {mode === 'series' ? (
                <DateRangeField
                  label="Series window"
                  value={ranges.series}
                  onChange={(range) => setRanges((previous) => ({ ...previous, series: range }))}
                  min={earliest}
                  maxDays={maxDays ?? undefined}
                  presets={[90, 180, 365]}
                  hint="A full season shows the shape of the curve, not just the current state."
                />
              ) : null}

              {mode === 'compare' ? (
                <>
                  <DateRangeField
                    label="Baseline period"
                    value={ranges.baseline}
                    onChange={(range) => setRanges((previous) => ({ ...previous, baseline: range }))}
                    min={earliest}
                    maxDays={maxDays ?? undefined}
                    presets={[14, 30, 60]}
                    hint="The reference the recent period is measured against."
                  />
                  <DateRangeField
                    label="Recent period"
                    value={ranges.recent}
                    onChange={(range) => setRanges((previous) => ({ ...previous, recent: range }))}
                    min={earliest}
                    maxDays={maxDays ?? undefined}
                    presets={[14, 30, 60]}
                    hint="Overlapping periods share scenes and will understate any change."
                  />
                </>
              ) : null}

              <CloudFilterSlider
                value={settings.cloudThreshold}
                onChange={(value) => patchSettings({ cloudThreshold: value })}
              />
            </div>
          </Panel>

          {mode === 'series' ? (
            <Panel title="Series options">
              <SeriesOptionsForm settings={settings} onChange={patchSettings} />
            </Panel>
          ) : null}

          {mode === 'compare' ? (
            <Panel title="Change options">
              <ChangeOptionsForm
                settings={settings}
                onChange={patchSettings}
                serverDefault={configData?.default_decline_threshold ?? null}
              />
            </Panel>
          ) : null}

          <Panel title="Processing" subtitle="Masking, compositing and scale">
            <AnalysisOptionsForm settings={settings} onChange={patchSettings} config={configData} />
          </Panel>

          <Panel title="Vegetation classes" subtitle="Configurable NDVI boundaries">
            <ThresholdEditor
              thresholds={settings.thresholds}
              isCustom={settings.thresholdsAreCustom}
              onChange={changeThresholds}
              config={configData}
              statistics={snapshotStatistics}
              classLabels={classLabels}
            />
          </Panel>

          <Panel title="Earth Engine" subtitle="Backend credential status">
            <SetupNotice
              status={health.data?.earth_engine ?? null}
              healthError={health.error}
              test={geeTest}
            />
          </Panel>

          <Panel title="Scope and limitations">
            <LimitationsPanel config={configData} />
          </Panel>

          <HistoryPanel refreshKey={historyRefreshKey} />
          <RegionalCoveragePanel />
        </aside>

        <main className="content">
          <ModeTabs mode={mode} onChange={setMode} />

          <div className="run-bar">
            <button
              type="button"
              className="button button--primary"
              onClick={() => void runActive()}
              disabled={activeTask.isLoading || blockingReason !== null}
            >
              {activeTask.isLoading
                ? 'Computing…'
                : mode === 'snapshot'
                  ? 'Compute NDVI'
                  : mode === 'series'
                    ? 'Build time series'
                    : 'Compare periods'}
            </button>
            {activeTask.isLoading ? (
              <button type="button" className="button button--ghost" onClick={activeTask.cancel}>
                Cancel
              </button>
            ) : null}
            {blockingReason ? <span className="run-bar__reason">{blockingReason}</span> : null}
          </div>

          <MapView
            aoi={aoi}
            onAOIChange={handleMapAOI}
            onAOIError={setDrawError}
            layers={layers}
            activeLayerId={activeLayerId}
            opacity={layerOpacity}
            fitBBox={fitBBox}
          />

          {layers.length > 0 ? (
            <Panel title="Map layers" subtitle="Earth Engine rasters for this result">
              <LayerSwitcher
                layers={layers}
                activeLayerId={activeLayerId}
                onActiveLayerChange={setSelectedLayerId}
                opacity={layerOpacity}
                onOpacityChange={setLayerOpacity}
              />
            </Panel>
          ) : null}

          {mode === 'snapshot' ? (
            <AsyncSection
              state={snapshot}
              onRetry={() => void runActive()}
              onCancel={snapshot.cancel}
              loadingMessage="Compositing scenes and computing NDVI…"
              errorAdvice={
                <p>
                  Windows shorter than a Sentinel-2 revisit, or a low scene cloud limit in a cloudy
                  season, are the usual reasons nothing is returned.
                </p>
              }
              empty={
                <EmptyState title="No analysis yet">
                  Draw a field, pick a date window, then press <strong>Compute NDVI</strong>.
                </EmptyState>
              }
            >
              {(result) => <SnapshotResults result={result} />}
            </AsyncSection>
          ) : null}

          {mode === 'series' ? (
            <AsyncSection
              state={series}
              onRetry={() => void runActive()}
              onCancel={series.cancel}
              loadingMessage="Reducing every scene in the window…"
              errorAdvice={
                <p>
                  A time series reduces one image per time step, so a long window with a fine time
                  step is the slowest request this dashboard makes.
                </p>
              }
              empty={
                <EmptyState title="No series yet">
                  Pick a window — a year works well — then press <strong>Build time series</strong>.
                </EmptyState>
              }
            >
              {(result) => <SeriesResults result={result} />}
            </AsyncSection>
          ) : null}

          {mode === 'compare' ? (
            <AsyncSection
              state={compare}
              onRetry={() => void runActive()}
              onCancel={compare.cancel}
              loadingMessage="Compositing both periods and differencing…"
              errorAdvice={
                <p>
                  Both periods need cloud-free imagery. If either is empty the comparison cannot be
                  made — widen that period rather than both.
                </p>
              }
              empty={
                <EmptyState title="No comparison yet">
                  Set a baseline and a recent period, then press <strong>Compare periods</strong>.
                </EmptyState>
              }
            >
              {(result) => <CompareResults result={result} />}
            </AsyncSection>
          ) : null}
        </main>
      </div>
    </div>
  )
}
