import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet-draw'
import { useMap } from 'react-leaflet'
import { parseAOIGeometry, roundGeometry } from '@/utils/geometry'
import type { AOIGeometry, Position } from '@/types/api'

interface AOIDrawControlProps {
  /**
   * The AOI to display. Kept controlled so the sidebar (pasted GeoJSON, "clear
   * AOI") and the map toolbar stay in sync instead of each holding a copy.
   */
  geometry: AOIGeometry | null
  /** Called with the new geometry, or `null` when the AOI is deleted. */
  onChange: (geometry: AOIGeometry | null) => void
  /** Called with a human-readable reason when a shape could not be used. */
  onError?: (message: string) => void
}

/** AOI outline colour. Amber reads clearly over both satellite and street tiles. */
const AOI_STYLE: L.PathOptions = {
  color: '#f5a623',
  weight: 3,
  opacity: 0.95,
  fillColor: '#f5a623',
  fillOpacity: 0.08,
}

/** Minimal shape of what `leaflet-draw` hands back; keeps us off `geojson` types. */
interface GeoJSONCapableLayer {
  toGeoJSON(): unknown
}

/** GeoJSON is [lon, lat]; Leaflet is [lat, lng]. This is where they swap. */
function toLatLngs(ring: Position[]): L.LatLngTuple[] {
  return ring.map(([lon, lat]) => [lat, lon])
}

/** Build a Leaflet layer for an AOI geometry, or `null` if unsupported. */
function geometryToLayer(geometry: AOIGeometry): L.Layer | null {
  switch (geometry.type) {
    case 'Point': {
      const [lon, lat] = geometry.coordinates
      return L.marker([lat, lon])
    }
    case 'Polygon':
      return L.polygon(geometry.coordinates.map(toLatLngs), AOI_STYLE)
    case 'MultiPolygon':
      return L.polygon(
        geometry.coordinates.map((rings) => rings.map(toLatLngs)),
        AOI_STYLE,
      )
    default:
      return null
  }
}

/**
 * AOI drawing, editing and deletion, wired straight to `leaflet-draw`.
 *
 * We drive `leaflet-draw` through `useMap()` rather than pulling in a React
 * wrapper package: the plugin is a handful of imperative calls and three events,
 * and the wrappers in this space are thin, frequently unmaintained, and lag
 * behind react-leaflet major versions.
 *
 * Design decisions worth knowing:
 *
 * - **One AOI at a time.** A new shape replaces the previous one. Every analysis
 *   endpoint takes a single AOI, so keeping two on the map would only raise the
 *   question of which one is being analysed.
 * - **Circle and polyline are disabled.** GeoJSON has no circle type, and a
 *   circle is better expressed as a `Point` plus the `buffer_m` request field,
 *   which the backend already supports. A polyline has no area to analyse.
 * - **`showArea: false`.** `leaflet-draw` 1.0.4's area tooltip calls
 *   `L.GeometryUtil.readableArea`, which assigns to an undeclared `type`
 *   variable. That is a tolerated implicit global in a `<script>` tag but a
 *   `ReferenceError` inside an ES module, which is how a bundler serves it. The
 *   AOI panel shows the area instead.
 */
export function AOIDrawControl({ geometry, onChange, onError }: AOIDrawControlProps) {
  const map = useMap()

  const groupRef = useRef<L.FeatureGroup | null>(null)
  /** Last geometry this control emitted, so incoming props do not echo back. */
  const publishedRef = useRef<string | null>(null)

  // Callbacks live in refs so the toolbar effect can key on `map` alone. Keying
  // it on the callbacks would rebuild the whole toolbar on every parent render.
  const onChangeRef = useRef(onChange)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onChangeRef.current = onChange
    onErrorRef.current = onError
  }, [onChange, onError])

  useEffect(() => {
    const drawnItems = new L.FeatureGroup()
    groupRef.current = drawnItems
    map.addLayer(drawnItems)

    const drawControl = new L.Control.Draw({
      position: 'topright',
      draw: {
        polygon: {
          allowIntersection: false,
          showArea: false,
          shapeOptions: AOI_STYLE,
          drawError: {
            color: '#d64545',
            message: 'Field boundaries cannot cross themselves.',
          },
        },
        rectangle: { showArea: false, shapeOptions: AOI_STYLE },
        marker: {},
        polyline: false,
        circle: false,
        circlemarker: false,
      },
      edit: {
        featureGroup: drawnItems,
        remove: true,
      },
    })
    map.addControl(drawControl)

    /** Read the single layer in the group and publish it as GeoJSON. */
    const publish = () => {
      const layer = drawnItems.getLayers()[0]
      if (!layer) {
        publishedRef.current = null
        onChangeRef.current(null)
        return
      }

      // Every shape leaflet-draw produces exposes toGeoJSON(); we keep the
      // result as `unknown` and validate it with the same parser used for
      // GeoJSON pasted in from outside the app.
      const raw = (layer as unknown as GeoJSONCapableLayer).toGeoJSON()
      const parsed = parseAOIGeometry(raw)

      if (!parsed.geometry) {
        onErrorRef.current?.(parsed.error ?? 'That shape could not be converted to GeoJSON.')
        return
      }

      const rounded = roundGeometry(parsed.geometry)
      publishedRef.current = JSON.stringify(rounded)
      onChangeRef.current(rounded)
    }

    const handleCreated = (event: L.LeafletEvent) => {
      const { layer } = event as L.DrawEvents.Created
      drawnItems.clearLayers()
      drawnItems.addLayer(layer)
      publish()
    }

    map.on(L.Draw.Event.CREATED, handleCreated)
    map.on(L.Draw.Event.EDITED, publish)
    map.on(L.Draw.Event.DELETED, publish)

    return () => {
      map.off(L.Draw.Event.CREATED, handleCreated)
      map.off(L.Draw.Event.EDITED, publish)
      map.off(L.Draw.Event.DELETED, publish)
      map.removeControl(drawControl)
      map.removeLayer(drawnItems)
      groupRef.current = null
    }
  }, [map])

  // Mirror externally-set geometry (pasted GeoJSON, "clear AOI") into the
  // editable group. Skipped when the incoming value is the one we just emitted,
  // which would otherwise replace the layer the user is still editing.
  useEffect(() => {
    const group = groupRef.current
    if (!group) return

    const serialized = geometry ? JSON.stringify(geometry) : null
    if (serialized === publishedRef.current) return

    group.clearLayers()
    if (geometry) {
      const layer = geometryToLayer(geometry)
      if (layer) group.addLayer(layer)
    }
    publishedRef.current = serialized
  }, [geometry])

  return null
}
