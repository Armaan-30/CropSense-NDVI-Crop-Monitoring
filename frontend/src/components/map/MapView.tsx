import 'leaflet/dist/leaflet.css'
import 'leaflet-draw/dist/leaflet.draw.css'
import '@/components/map/leafletSetup'

import { LayersControl, MapContainer, TileLayer } from 'react-leaflet'
import { AnalysisPane, ANALYSIS_PANE } from '@/components/map/AnalysisPane'
import { AOIDrawControl } from '@/components/map/AOIDrawControl'
import { BASEMAPS } from '@/components/map/leafletSetup'
import { FitBounds } from '@/components/map/FitBounds'
import { LayerLegend } from '@/components/map/LayerLegend'
import { DEFAULT_MAP_CENTER, DEFAULT_MAP_ZOOM } from '@/utils/env'
import type { AOIGeometry, MapLayer } from '@/types/api'

interface MapViewProps {
  aoi: AOIGeometry | null
  onAOIChange: (geometry: AOIGeometry | null) => void
  onAOIError?: (message: string) => void
  /** Layers returned by the most recent analysis. May be empty. */
  layers: MapLayer[]
  /** `id` of the overlay to display, or `null` for none. */
  activeLayerId: string | null
  /** Overlay opacity, 0-1. */
  opacity: number
  /** `[minLon, minLat, maxLon, maxLat]` to zoom to, from the server AOI summary. */
  fitBBox: number[] | null
}

/**
 * The map: basemaps, AOI drawing, and the active Earth Engine overlay.
 *
 * `tile_url_template` values are signed and short-lived, so the overlay
 * `TileLayer` is keyed on the URL. That forces a fresh Leaflet layer when a new
 * analysis returns instead of Leaflet trying to reuse the old tile cache under
 * a new URL.
 */
export function MapView({
  aoi,
  onAOIChange,
  onAOIError,
  layers,
  activeLayerId,
  opacity,
  fitBBox,
}: MapViewProps) {
  const activeLayer = layers.find((layer) => layer.id === activeLayerId) ?? null
  const trueColor = layers.find((layer) => layer.id === 'true_color') ?? null

  return (
    <div className="map">
      <MapContainer
        center={[DEFAULT_MAP_CENTER[0], DEFAULT_MAP_CENTER[1]]}
        zoom={DEFAULT_MAP_ZOOM}
        className="map__canvas"
        scrollWheelZoom
      >
        <LayersControl position="topleft">
          <LayersControl.BaseLayer name={BASEMAPS.satellite.name} checked>
            <TileLayer
              url={BASEMAPS.satellite.url}
              attribution={BASEMAPS.satellite.attribution}
              maxZoom={BASEMAPS.satellite.maxZoom}
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name={BASEMAPS.street.name}>
            <TileLayer
              url={BASEMAPS.street.url}
              attribution={BASEMAPS.street.attribution}
              maxZoom={BASEMAPS.street.maxZoom}
            />
          </LayersControl.BaseLayer>

          {/* Sentinel-2 natural colour, when the analysis produced it. Offered as
              a checkbox rather than a basemap so it can sit under the NDVI
              overlay for a like-for-like visual cross-check. */}
          {trueColor ? (
            <LayersControl.Overlay name="Sentinel-2 true colour">
              <TileLayer
                key={trueColor.tile_url_template}
                url={trueColor.tile_url_template}
                attribution={trueColor.attribution}
              />
            </LayersControl.Overlay>
          ) : null}
        </LayersControl>

        <AnalysisPane />

        {activeLayer ? (
          <TileLayer
            key={activeLayer.tile_url_template}
            url={activeLayer.tile_url_template}
            attribution={activeLayer.attribution}
            opacity={opacity}
            pane={ANALYSIS_PANE}
          />
        ) : null}

        <AOIDrawControl geometry={aoi} onChange={onAOIChange} onError={onAOIError} />
        <FitBounds bbox={fitBBox} />
      </MapContainer>

      {activeLayer ? (
        <div className="map__legend">
          <LayerLegend layer={activeLayer} />
        </div>
      ) : null}

      {!aoi ? (
        <div className="map__hint">
          <strong>Draw a field to begin.</strong> Use the polygon or rectangle tool (top right), or
          drop a marker and set a buffer radius in the sidebar.
        </div>
      ) : null}
    </div>
  )
}
