import assert from 'node:assert/strict'
import test from 'node:test'
import {
  approximateAreaHa,
  bufferAreaHa,
  geometryBBox,
  parseAOIGeometry,
  roundGeometry,
} from '../src/utils/geometry.ts'

const field = {
  type: 'Polygon',
  coordinates: [[[75.8, 30.9], [75.801, 30.9], [75.801, 30.901], [75.8, 30.901], [75.8, 30.9]]],
}

test('GeoJSON parser accepts a valid polygon and a single-feature envelope', () => {
  assert.deepEqual(parseAOIGeometry(field), { geometry: field, error: null })
  assert.deepEqual(parseAOIGeometry({ type: 'Feature', geometry: field, properties: {} }), {
    geometry: field,
    error: null,
  })
})

test('GeoJSON parser rejects unsupported and multi-feature inputs', () => {
  assert.match(parseAOIGeometry({ type: 'LineString', coordinates: [] }).error, /Unsupported geometry/)
  assert.match(
    parseAOIGeometry({ type: 'FeatureCollection', features: [{ geometry: field }, { geometry: field }] }).error,
    /exactly one feature/,
  )
})

test('geometry helpers estimate a field, bounds, point buffer, and coordinate rounding', () => {
  const area = approximateAreaHa(field)
  assert.ok(area > 0.9 && area < 1.1, `unexpected ~1 ha field estimate: ${area}`)
  assert.deepEqual(geometryBBox(field), [75.8, 30.9, 75.801, 30.901])
  assert.ok(bufferAreaHa(100) > 3.1 && bufferAreaHa(100) < 3.2)
  assert.deepEqual(roundGeometry({ type: 'Point', coordinates: [75.8000004, 30.9000004] }), {
    type: 'Point',
    coordinates: [75.8, 30.9],
  })
})
