/**
 * GeoJSON geometry helpers.
 *
 * Deliberately free of any Leaflet import so the maths stays testable and the
 * map components own the Leaflet-specific conversions.
 *
 * Areas computed here are for immediate UI feedback only ("that field looks
 * like ~12 ha, which is within the server limit"). The authoritative area is
 * always the `aoi.area_ha` the backend returns, which Earth Engine computes on
 * the same geometry it actually analysed - including the buffer.
 */

import type { AOIGeometry, Position } from '@/types/api'

/** WGS 84 semi-major axis, metres. */
const EARTH_RADIUS_M = 6_378_137
const DEG_TO_RAD = Math.PI / 180

/**
 * Geodesic area of a closed ring, in square metres.
 *
 * Spherical-excess formula, the same one Leaflet.draw uses, so the number the
 * user sees while drawing matches what other Leaflet tools would report. Good
 * to well under a percent at field scale; not suitable for continent-scale
 * polygons.
 */
export function ringAreaM2(ring: Position[]): number {
  const count = ring.length
  if (count < 3) return 0

  let area = 0
  for (let i = 0; i < count; i += 1) {
    const p1 = ring[i]
    const p2 = ring[(i + 1) % count]
    if (!p1 || !p2) continue
    const [lon1, lat1] = p1
    const [lon2, lat2] = p2
    area += (lon2 - lon1) * DEG_TO_RAD * (2 + Math.sin(lat1 * DEG_TO_RAD) + Math.sin(lat2 * DEG_TO_RAD))
  }
  return Math.abs((area * EARTH_RADIUS_M * EARTH_RADIUS_M) / 2)
}

/**
 * Approximate area of a geometry in hectares.
 *
 * Interior rings (holes) are subtracted. A `Point` has no area - callers that
 * buffer a point should compute πr² themselves, since the buffer is a request
 * parameter rather than a property of the geometry.
 */
export function approximateAreaHa(geometry: AOIGeometry): number {
  const polygonAreaM2 = (rings: Position[][]): number =>
    rings.reduce((total, ring, index) => {
      const area = ringAreaM2(ring)
      return index === 0 ? total + area : total - area
    }, 0)

  switch (geometry.type) {
    case 'Polygon':
      return polygonAreaM2(geometry.coordinates) / 10_000
    case 'MultiPolygon':
      return geometry.coordinates.reduce((total, rings) => total + polygonAreaM2(rings), 0) / 10_000
    case 'Point':
      return 0
  }
}

/** Area of a circular buffer around a point, in hectares. */
export function bufferAreaHa(bufferM: number): number {
  return (Math.PI * bufferM * bufferM) / 10_000
}

/** Every position in a geometry, flattened. */
function allPositions(geometry: AOIGeometry): Position[] {
  switch (geometry.type) {
    case 'Point':
      return [geometry.coordinates]
    case 'Polygon':
      return geometry.coordinates.flat()
    case 'MultiPolygon':
      return geometry.coordinates.flat(2)
  }
}

/** Bounding box as `[minLon, minLat, maxLon, maxLat]`, or `null` if empty. */
export function geometryBBox(
  geometry: AOIGeometry,
): [number, number, number, number] | null {
  const positions = allPositions(geometry)
  if (positions.length === 0) return null

  let minLon = Infinity
  let minLat = Infinity
  let maxLon = -Infinity
  let maxLat = -Infinity

  for (const position of positions) {
    const [lon, lat] = position
    if (lon < minLon) minLon = lon
    if (lon > maxLon) maxLon = lon
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
  }

  if (!Number.isFinite(minLon) || !Number.isFinite(minLat)) return null
  return [minLon, minLat, maxLon, maxLat]
}

/** Centroid of the bounding box as `[lon, lat]`. Cheap, not area-weighted. */
export function geometryCenter(geometry: AOIGeometry): Position | null {
  const bbox = geometryBBox(geometry)
  if (!bbox) return null
  const [minLon, minLat, maxLon, maxLat] = bbox
  return [(minLon + maxLon) / 2, (minLat + maxLat) / 2]
}

/** Number of vertices, used to warn about over-detailed uploaded geometry. */
export function vertexCount(geometry: AOIGeometry): number {
  return allPositions(geometry).length
}

/**
 * Close a ring if the caller left it open.
 *
 * Leaflet's `toGeoJSON()` already closes rings, but hand-written or uploaded
 * GeoJSON often does not, and the backend requires at least four positions
 * with the first repeated at the end.
 */
export function closeRing(ring: Position[]): Position[] {
  if (ring.length === 0) return ring
  const first = ring[0]
  const last = ring[ring.length - 1]
  if (!first || !last) return ring
  if (first[0] === last[0] && first[1] === last[1]) return ring
  return [...ring, first]
}

/** Round coordinates to a fixed precision to keep request payloads small. */
export function roundGeometry(geometry: AOIGeometry, decimals = 6): AOIGeometry {
  const factor = 10 ** decimals
  const roundPosition = (position: Position): Position => [
    Math.round(position[0] * factor) / factor,
    Math.round(position[1] * factor) / factor,
  ]

  switch (geometry.type) {
    case 'Point':
      return { type: 'Point', coordinates: roundPosition(geometry.coordinates) }
    case 'Polygon':
      return {
        type: 'Polygon',
        coordinates: geometry.coordinates.map((ring) => ring.map(roundPosition)),
      }
    case 'MultiPolygon':
      return {
        type: 'MultiPolygon',
        coordinates: geometry.coordinates.map((rings) => rings.map((ring) => ring.map(roundPosition))),
      }
  }
}

/** Short human description of an AOI, e.g. "Polygon · 12 vertices". */
export function describeGeometry(geometry: AOIGeometry): string {
  if (geometry.type === 'Point') {
    const [lon, lat] = geometry.coordinates
    return `Point · ${lat.toFixed(5)}, ${lon.toFixed(5)}`
  }
  return `${geometry.type} · ${vertexCount(geometry)} vertices`
}

// ---------------------------------------------------------------------------
// Parsing untrusted GeoJSON
// ---------------------------------------------------------------------------

export interface GeometryParseResult {
  geometry: AOIGeometry | null
  /** Human-readable reason the input was rejected, or `null` on success. */
  error: string | null
}

function fail(message: string): GeometryParseResult {
  return { geometry: null, error: message }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

/** Validate and normalise one `[lon, lat]` position. */
function parsePosition(value: unknown): Position | null {
  if (!Array.isArray(value) || value.length < 2) return null
  const lon = value[0]
  const lat = value[1]
  if (typeof lon !== 'number' || typeof lat !== 'number') return null
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null
  if (lon < -180 || lon > 180 || lat < -90 || lat > 90) return null
  return [lon, lat]
}

/** Validate a polygon coordinate array (array of linear rings). */
function parseRings(value: unknown, label: string): { rings: Position[][] } | { error: string } {
  if (!Array.isArray(value) || value.length === 0) {
    return { error: `${label} must be a non-empty array of linear rings.` }
  }

  const rings: Position[][] = []
  for (let index = 0; index < value.length; index += 1) {
    const raw = value[index]
    if (!Array.isArray(raw)) {
      return { error: `${label}: ring ${index} is not an array of positions.` }
    }
    const positions: Position[] = []
    for (const entry of raw) {
      const position = parsePosition(entry)
      if (!position) {
        return { error: `${label}: ring ${index} contains an invalid [longitude, latitude] pair.` }
      }
      positions.push(position)
    }
    const closed = closeRing(positions)
    if (closed.length < 4) {
      return {
        error: `${label}: ring ${index} needs at least 3 distinct corners (got ${positions.length}).`,
      }
    }
    rings.push(closed)
  }
  return { rings }
}

/**
 * Parse arbitrary GeoJSON into an AOI geometry, mirroring the backend's rules.
 *
 * Accepts a bare geometry, a `Feature`, or a single-feature `FeatureCollection`
 * — exactly what `backend/app/schemas/aoi.py` accepts. Validating here as well
 * as server-side is not redundant: it turns a round trip and a 422 into instant
 * feedback while the user is still looking at the field they drew.
 *
 * Coordinates must be EPSG:4326 with longitude first, per the GeoJSON spec.
 */
export function parseAOIGeometry(input: unknown): GeometryParseResult {
  const record = asRecord(input)
  if (!record) return fail('Expected a GeoJSON object.')

  const type = record['type']
  if (typeof type !== 'string') return fail('GeoJSON object is missing a "type".')

  if (type === 'FeatureCollection') {
    const features = record['features']
    if (!Array.isArray(features) || features.length === 0) {
      return fail('FeatureCollection contains no features.')
    }
    if (features.length !== 1) {
      return fail(
        `FeatureCollection must contain exactly one feature (got ${features.length}). ` +
          'Analyse one field at a time.',
      )
    }
    return parseAOIGeometry(features[0])
  }

  if (type === 'Feature') {
    const geometry = record['geometry']
    if (!asRecord(geometry)) return fail('Feature has no geometry.')
    return parseAOIGeometry(geometry)
  }

  const coordinates = record['coordinates']

  if (type === 'Point') {
    const position = parsePosition(coordinates)
    if (!position) return fail('Point coordinates must be [longitude, latitude].')
    return { geometry: { type: 'Point', coordinates: position }, error: null }
  }

  if (type === 'Polygon') {
    const parsed = parseRings(coordinates, 'Polygon coordinates')
    if ('error' in parsed) return fail(parsed.error)
    return { geometry: { type: 'Polygon', coordinates: parsed.rings }, error: null }
  }

  if (type === 'MultiPolygon') {
    if (!Array.isArray(coordinates) || coordinates.length === 0) {
      return fail('MultiPolygon coordinates must be a non-empty array of polygons.')
    }
    const polygons: Position[][][] = []
    for (let index = 0; index < coordinates.length; index += 1) {
      const parsed = parseRings(coordinates[index], `MultiPolygon polygon ${index}`)
      if ('error' in parsed) return fail(parsed.error)
      polygons.push(parsed.rings)
    }
    return { geometry: { type: 'MultiPolygon', coordinates: polygons }, error: null }
  }

  return fail(
    `Unsupported geometry type "${type}". Use Polygon, MultiPolygon or Point ` +
      '(optionally wrapped in a Feature or single-feature FeatureCollection).',
  )
}
