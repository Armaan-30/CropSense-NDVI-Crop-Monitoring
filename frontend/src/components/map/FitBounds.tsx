import { useEffect } from 'react'
import L from 'leaflet'
import { useMap } from 'react-leaflet'

interface FitBoundsProps {
  /** `[minLon, minLat, maxLon, maxLat]`, GeoJSON order. `null` does nothing. */
  bbox: number[] | null
  /** Never zoom in past this level, so a tiny plot does not fill the screen. */
  maxZoom?: number
}

/**
 * Pan and zoom the map to a bounding box when it changes.
 *
 * Keyed on the serialised bbox rather than the array identity: the parent
 * rebuilds the array on every render, and refitting on each one would fight the
 * user for control of the viewport.
 */
export function FitBounds({ bbox, maxZoom = 17 }: FitBoundsProps) {
  const map = useMap()
  const key = bbox ? bbox.join(',') : null

  useEffect(() => {
    if (!key) return
    const parts = key.split(',').map(Number)
    const [minLon, minLat, maxLon, maxLat] = parts
    if (
      minLon === undefined ||
      minLat === undefined ||
      maxLon === undefined ||
      maxLat === undefined
    ) {
      return
    }

    // A Point AOI has a zero-area bbox; fitBounds would slam to max zoom.
    if (minLon === maxLon && minLat === maxLat) {
      map.setView([minLat, minLon], Math.min(16, maxZoom))
      return
    }

    map.fitBounds(
      L.latLngBounds([minLat, minLon], [maxLat, maxLon]),
      { padding: [24, 24], maxZoom },
    )
  }, [key, map, maxZoom])

  return null
}
