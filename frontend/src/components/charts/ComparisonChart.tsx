import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TooltipContentProps } from 'recharts'
import { formatArea, formatPercent } from '@/utils/format'
import type { HealthSummary } from '@/types/api'

interface ComparisonChartProps {
  baseline: HealthSummary
  recent: HealthSummary
  height?: number
}

interface ComparisonRow {
  label: string
  classColor: string
  baselinePercent: number
  recentPercent: number
  baselineAreaHa: number
  recentAreaHa: number
  shift: number
}

const COLOR_BASELINE = '#7d8894'
const COLOR_RECENT = '#4caf50'

function ComparisonTooltip({ active, payload }: TooltipContentProps) {
  if (!active) return null
  const row = payload[0]?.payload as ComparisonRow | undefined
  if (!row) return null

  const sign = row.shift > 0 ? '+' : ''
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip__title">
        <span className="swatch" style={{ backgroundColor: row.classColor }} aria-hidden="true" />
        {row.label}
      </p>
      <p className="chart-tooltip__row">
        Baseline {formatPercent(row.baselinePercent)} · {formatArea(row.baselineAreaHa)}
      </p>
      <p className="chart-tooltip__row">
        Recent {formatPercent(row.recentPercent)} · {formatArea(row.recentAreaHa)}
      </p>
      <p className="chart-tooltip__row chart-tooltip__muted">
        Shift {sign}
        {row.shift.toFixed(1)} percentage points
      </p>
    </div>
  )
}

/**
 * Class distribution in the baseline period against the recent period.
 *
 * Percentages are of each period's own classified area, which is what makes the
 * two comparable when different amounts of cloud were masked in each. Absolute
 * hectares appear in the tooltip, where the differing denominators can be seen.
 *
 * The bars are coloured by *period*, not by class: the question this chart
 * answers is "did the split shift?", and two greens side by side would make that
 * harder to read. The class's own palette colour is in the tooltip.
 */
export function ComparisonChart({ baseline, recent, height = 260 }: ComparisonChartProps) {
  const recentByKey = new Map(recent.classes.map((entry) => [entry.key, entry]))

  const rows: ComparisonRow[] = baseline.classes.map((entry) => {
    const match = recentByKey.get(entry.key)
    const recentPercent = match?.percent_of_valid ?? 0
    return {
      label: entry.label,
      classColor: entry.color,
      baselinePercent: Number(entry.percent_of_valid.toFixed(2)),
      recentPercent: Number(recentPercent.toFixed(2)),
      baselineAreaHa: entry.area_ha,
      recentAreaHa: match?.area_ha ?? 0,
      shift: Number((recentPercent - entry.percent_of_valid).toFixed(2)),
    }
  })

  const hasData = rows.some((row) => row.baselinePercent > 0 || row.recentPercent > 0)
  if (!hasData) {
    return <p className="hint">Neither period produced a classified area to compare.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
        <CartesianGrid stroke="#2a2f36" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="#8a9099" interval={0} />
        <YAxis
          tick={{ fontSize: 11 }}
          stroke="#8a9099"
          tickFormatter={(value: number) => `${value}%`}
        />
        <Tooltip content={ComparisonTooltip} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar
          dataKey="baselinePercent"
          name="Baseline"
          fill={COLOR_BASELINE}
          radius={[3, 3, 0, 0]}
          isAnimationActive={false}
        />
        <Bar
          dataKey="recentPercent"
          name="Recent"
          fill={COLOR_RECENT}
          radius={[3, 3, 0, 0]}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}
