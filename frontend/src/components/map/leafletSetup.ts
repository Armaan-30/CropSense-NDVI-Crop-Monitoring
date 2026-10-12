/**
 * One-time Leaflet setup that has to happen before any map renders.
 *
 * Leaflet resolves its default marker images relative to the CSS file at
 * runtime, which does not survive bundling and hashing - markers come out as
 * broken images. Importing the assets explicitly lets Vite fingerprint them and
 * hands Leaflet the real URLs.
 *
 * Importing this module for its side effect is enough; it is idempotent.
 */

import L from 'leaflet'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
})

/** Basemap definitions. Both require their attribution to be displayed. */
export const BASEMAPS = {
  street: {
    name: 'Street map',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  },
  satellite: {
    name: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution:
      'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
    maxZoom: 19,
  },
} as const
