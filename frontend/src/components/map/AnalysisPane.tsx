import { useEffect } from 'react'
import { useMap } from 'react-leaflet'

/**
 * Dedicated Leaflet pane for Earth Engine analysis rasters.
 *
 * Without this, the NDVI overlay and the AOI outline both land in
 * `overlayPane` and their stacking depends on insertion order - so an overlay
 * added after the AOI hides the field boundary the user just drew. A pane at
 * z-index 350 sits above the basemap tiles (200) and below all vector overlays
 * (400), which is the order we want regardless of when layers are added.
 */
export const ANALYSIS_PANE = 'cropsense-analysis'

export function AnalysisPane() {
  const map = useMap()

  useEffect(() => {
    if (map.getPane(ANALYSIS_PANE)) return
    const pane = map.createPane(ANALYSIS_PANE)
    pane.style.zIndex = '350'
    // Raster overlays are not interactive; let clicks reach the map and the AOI.
    pane.style.pointerEvents = 'none'
  }, [map])

  return null
}
