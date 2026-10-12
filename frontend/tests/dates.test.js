import assert from 'node:assert/strict'
import test from 'node:test'
import {
  addDays,
  daysBetween,
  earliestDateFor,
  isOrderedRange,
  recentWindow,
} from '../src/utils/dates.ts'

test('date windows count both endpoints and cross month boundaries', () => {
  assert.equal(daysBetween('2026-01-30', '2026-02-02'), 4)
  assert.equal(addDays('2026-01-31', 1), '2026-02-01')
})

test('range validation rejects reversed and malformed dates', () => {
  assert.equal(isOrderedRange('2026-01-01', '2026-01-01'), true)
  assert.equal(isOrderedRange('2026-02-02', '2026-02-01'), false)
  assert.equal(isOrderedRange('not-a-date', '2026-02-01'), false)
})

test('recent windows are inclusive and cloud-mask dates respect coverage', () => {
  const range = recentWindow(30)
  assert.equal(daysBetween(range.start_date, range.end_date), 30)
  assert.equal(earliestDateFor('cs_plus'), '2017-06-27')
  assert.equal(earliestDateFor('scl'), '2017-03-28')
})
