import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TooltipContentProps } from 'recharts'
import { fromISODate } from '@/utils/dates'
import { formatDate, formatFraction, formatNDVI } from '@/utils/format'
import type { TimeSeriesPoint, TrendSummary } from '@/types/api'

interface TimeSeriesChartProps {
  points: TimeSeriesPoint[]
  trend: TrendSummary | null
  height?: number
}

interface SeriesRow {
  /** Epoch milliseconds - a numeric x axis keeps irregular revisits correctly spaced. */
  t: number
  date: string
  mean: number | null
  min: number | null
  max: number | null
  median: number | null
  fit: number | null
  validFraction: number | null
  sceneCount: number
  sceneCloud: number | null
}

const MS_PER_DAY = 86_400_000

const COLOR_MEAN = '#4caf50'
const COLOR_ENVELOPE = '#7f9c86'
const COLOR_FIT = '#e8a33d'

function SeriesTooltip({ active, payload }: TooltipContentProps) {
  if (!active) return null
  const row = payload[0]?.payload as SeriesRow | undefined
  if (!row) return null

  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip__title">{formatDate(row.date)}</p>
      <p className="chart-tooltip__row">
        Mean NDVI <strong>{formatNDVI(row.mean)}</strong>
      </p>
      <p className="chart-tooltip__row">
        Range {formatNDVI(row.min, 2)} – {formatNDVI(row.max, 2)}
      </p>
      <p className="chart-tooltip__row">Median {formatNDVI(row.median)}</p>
      <p className="chart-tooltip__row chart-tooltip__muted">
        {formatFraction(row.validFraction)} cloud-free ·{' '}
        {row.sceneCount === 1 ? '1 scene' : `${row.sceneCount} scenes`}
      </p>
      {row.fit !== null ? (
        <p className="chart-tooltip__row chart-tooltip__muted">Trend fit {formatNDVI(row.fit)}</p>
      ) : null}
    </div>
  )
}

/**
 * Mean NDVI over time, with the per-step min/max envelope and the fitted trend.
 *
 * Two deliberate choices:
 *
 * - The x axis is numeric (epoch milliseconds) rather than categorical, so a
 *   six-week cloud gap looks like a six-week gap. On a category axis every
 *   observation is equally spaced and a sparse winter reads as a dense series.
 * - `connectNulls` is off for the observed series. A missing step means no
 *   cloud-free observation, and drawing a line through it would invent data.
 *   The fitted trend line does connect across gaps - it is a model, not data.
 */
export function TimeSeriesChart({ points, trend, height = 300 }: TimeSeriesChartProps) {
  const usable = points.filter((point) => point.mean_ndvi !== null)
  const firstUsableDate = usable[0]?.date ?? null

  // The backend fits days-elapsed-since-the-first-usable-observation, so the
  // reported intercept is only meaningful in that same coordinate system.
  const slope = trend?.slope_ndvi_per_day ?? null
  const intercept = trend?.intercept ?? null
  const origin = firstUsableDate ? fromISODate(firstUsableDate).getTime() : null
  const canFit = slope !== null && intercept !== null && origin !== null && !Number.isNaN(origin)

  const rows: SeriesRow[] = points.map((point) => {
    const t = fromISODate(point.date).getTime()
    const elapsedDays = canFit && origin !== null ? (t - origin) / MS_PER_DAY : null
    return {
      t,
      date: point.date,
      mean: point.mean_ndvi,
      min: point.min_ndvi,
      max: point.max_ndvi,
      median: point.median_ndvi,
      fit:
        elapsedDays !== null && slope !== null && intercept !== null
          ? intercept + slope * elapsedDays
          : null,
      validFraction: point.valid_pixel_fraction,
      sceneCount: point.scene_count,
      sceneCloud: point.scene_cloud_percent,
    }
  })

  if (rows.length === 0) {
    return <p className="hint">No time steps to plot.</p>
  }

  const values = rows.flatMap((row) =>
    [row.min, row.max, row.mean, row.fit].filter((value): value is number => value !== null),
  )
  const lowest = values.length > 0 ? Math.min(...values) : 0
  const highest = values.length > 0 ? Math.max(...values) : 1
  const pad = Math.max(0.05, (highest - lowest) * 0.1)
  const domain: [number, number] = [
    Math.max(-1, Number((lowest - pad).toFixed(2))),
    Math.min(1, Number((highest + pad).toFixed(2))),
  ]

  return (
    <div className="stack stack--tight">
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
          <CartesianGrid stroke="#2a2f36" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(value: number) =>
              new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
            }
            tick={{ fontSize: 11 }}
            stroke="#8a9099"
            minTickGap={28}
          />
          <YAxis
            domain={domain}
            tick={{ fontSize: 11 }}
            stroke="#8a9099"
            tickFormatter={(value: number) => value.toFixed(2)}
          />
          {domain[0] < 0 && domain[1] > 0 ? (
            <ReferenceLine y={0} stroke="#4a5058" strokeDasharray="2 3" />
          ) : null}
          <Tooltip content={SeriesTooltip} />

          {/* Envelope drawn as two thin lines rather than a shaded band: the band
              would have to be stacked, and stacking breaks at the cloud gaps. */}
          <Line
            dataKey="max"
            name="Max"
            stroke={COLOR_ENVELOPE}
            strokeWidth={1}
            strokeDasharray="3 3"
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
          <Line
            dataKey="min"
            name="Min"
            stroke={COLOR_ENVELOPE}
            strokeWidth={1}
            strokeDasharray="3 3"
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
          {canFit ? (
            <Line
              dataKey="fit"
              name="Linear trend"
              stroke={COLOR_FIT}
              strokeWidth={1.5}
              strokeDasharray="6 4"
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          ) : null}
          <Line
            dataKey="mean"
            name="Mean NDVI"
            stroke={COLOR_MEAN}
            strokeWidth={2}
            dot={{ r: 3, fill: COLOR_MEAN, stroke: COLOR_MEAN }}
            activeDot={{ r: 5 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      <ul className="chart-legend">
        <li>
          <span className="chart-legend__line" style={{ background: COLOR_MEAN }} /> Mean NDVI
        </li>
        <li>
          <span
            className="chart-legend__line chart-legend__line--dashed"
            style={{ borderTopColor: COLOR_ENVELOPE }}
          />{' '}
          Min / max within the field
        </li>
        {canFit ? (
          <li>
            <span
              className="chart-legend__line chart-legend__line--dashed"
              style={{ borderTopColor: COLOR_FIT }}
            />{' '}
            Linear trend
          </li>
        ) : null}
      </ul>
    </div>
  )
}
