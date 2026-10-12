import { useState } from 'react'
import { Callout } from '@/components/common/Callout'
import {
  approximateAreaHa,
  bufferAreaHa,
  describeGeometry,
  parseAOIGeometry,
  roundGeometry,
} from '@/utils/geometry'
import { formatArea } from '@/utils/format'
import type { AOIGeometry, AOISummary } from '@/types/api'

/** Small demo rectangle near Jalgaon for trying the real Sentinel-2 workflow. */
const MAHARASHTRA_DEMO_AOI: AOIGeometry = {
  type: 'Polygon',
  coordinates: [
    [[75.55, 21.0], [75.551, 21.0], [75.551, 21.001], [75.55, 21.001], [75.55, 21.0]],
  ],
}

interface AOIPanelProps {
  aoi: AOIGeometry | null
  /** Current buffer setting, so a marker AOI can report a meaningful area. */
  bufferM: number
  onChange: (geometry: AOIGeometry | null) => void
  /** Server limit from `/api/system/config`, in km². */
  maxAreaKm2: number | null
  /** Server-computed AOI summary from the last analysis, if any. */
  summary: AOISummary | null
  /** Message from the map when a drawn shape could not be used. */
  drawError: string | null
}

/**
 * AOI summary, clear action and a GeoJSON paste box.
 *
 * The area shown before an analysis is computed in the browser and labelled as
 * an estimate. Once the server has run, its own `area_ha` is shown instead: that
 * is the area Earth Engine actually analysed, including the buffer, and it is
 * the figure every statistic and hectare count in the results refers to.
 */
export function AOIPanel({
  aoi,
  bufferM,
  onChange,
  maxAreaKm2,
  summary,
  drawError,
}: AOIPanelProps) {
  const [pasteOpen, setPasteOpen] = useState(false)
  const [pasteText, setPasteText] = useState('')
  const [pasteError, setPasteError] = useState<string | null>(null)

  const localAreaHa = aoi
    ? aoi.type === 'Point'
      ? bufferAreaHa(bufferM)
      : approximateAreaHa(aoi)
    : 0
  const overLimit = maxAreaKm2 !== null && localAreaHa / 100 > maxAreaKm2

  const applyPaste = () => {
    let parsedJson: unknown
    try {
      parsedJson = JSON.parse(pasteText)
    } catch (error) {
      setPasteError(`Not valid JSON: ${error instanceof Error ? error.message : String(error)}`)
      return
    }
    const { geometry, error } = parseAOIGeometry(parsedJson)
    if (!geometry) {
      setPasteError(error ?? 'Unsupported GeoJSON.')
      return
    }
    setPasteError(null)
    setPasteText('')
    setPasteOpen(false)
    onChange(roundGeometry(geometry))
  }

  return (
    <div className="stack">
      {drawError ? <Callout variant="warning">{drawError}</Callout> : null}

      {aoi ? (
        <dl className="kv">
          <dt>Geometry</dt>
          <dd>{describeGeometry(aoi)}</dd>

          <dt>{summary ? 'Analysed area' : 'Estimated area'}</dt>
          <dd>
            {summary ? formatArea(summary.area_ha) : formatArea(localAreaHa)}
            {!summary ? <small> (browser estimate)</small> : null}
          </dd>

          {aoi.type === 'Point' && bufferM === 0 ? (
            <>
              <dt>Buffer</dt>
              <dd className="kv__warn">
                A marker with a 0 m buffer has no area — set a buffer radius below.
              </dd>
            </>
          ) : null}

          {summary ? (
            <>
              <dt>Centroid</dt>
              <dd>
                {summary.centroid[1]?.toFixed(5)}, {summary.centroid[0]?.toFixed(5)}
              </dd>
            </>
          ) : null}
        </dl>
      ) : (
        <p className="hint">
          No field selected. Draw a polygon or rectangle on the map, drop a marker, or paste GeoJSON
          below.
        </p>
      )}

      {overLimit && maxAreaKm2 !== null ? (
        <Callout variant="warning" title="Area exceeds the server limit">
          This shape is about {(localAreaHa / 100).toFixed(1)} km², over the {maxAreaKm2} km² limit.
          The request will be rejected — draw a smaller area or split the work into parts.
        </Callout>
      ) : null}

      <div className="chip-row">
        <button
          type="button"
          className="chip"
          onClick={() => onChange(MAHARASHTRA_DEMO_AOI)}
          aria-label="Load demo area near Jalgaon, Maharashtra"
        >
          Use Maharashtra demo area
        </button>
        <button type="button" className="chip" disabled={!aoi} onClick={() => onChange(null)}>
          Clear field
        </button>
        <button type="button" className="chip" onClick={() => setPasteOpen((open) => !open)}>
          {pasteOpen ? 'Cancel paste' : 'Paste GeoJSON'}
        </button>
      </div>

      <p className="hint">
        The demo is a small rectangle for testing the live imagery workflow, not a surveyed farm
        boundary. Draw your own field or paste an authorized boundary for field-level results.
      </p>

      {pasteOpen ? (
        <div className="stack">
          <label className="field">
            <span className="field__label">GeoJSON</span>
            <textarea
              className="textarea"
              rows={6}
              value={pasteText}
              spellCheck={false}
              placeholder='{"type":"Polygon","coordinates":[[[75.55,21.0],[75.551,21.0],[75.551,21.001],[75.55,21.001],[75.55,21.0]]]}'
              onChange={(event) => setPasteText(event.target.value)}
            />
            <p className="field__hint">
              A Polygon, MultiPolygon or Point — optionally wrapped in a Feature or a single-feature
              FeatureCollection. Coordinates must be EPSG:4326 with longitude first.
            </p>
          </label>
          {pasteError ? <p className="field__error">{pasteError}</p> : null}
          <button
            type="button"
            className="button button--secondary"
            disabled={pasteText.trim() === ''}
            onClick={applyPaste}
          >
            Use this geometry
          </button>
        </div>
      ) : null}
    </div>
  )
}
