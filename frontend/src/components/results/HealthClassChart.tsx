import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TooltipContentProps } from 'recharts'
import { formatArea, formatNDVIRange, formatPercent } from '@/utils/format'
import type { HealthClassStat } from '@/types/api'

interface HealthClassChartProps {
  classes: HealthClassStat[]
  /** Chart height in pixels. */
  height?: number
}

interface ClassRow {
  label: string
  color: string
  areaHa: number
  percent: number
  ndviRange: string
}

function ClassTooltip({ active, payload }: TooltipContentProps) {
  if (!active) return null
  const row = payload[0]?.payload as ClassRow | undefined
  if (!row) return null

  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip__title">
        <span className="swatch" style={{ backgroundColor: row.color }} aria-hidden="true" />
        {row.label}
      </p>
      <p className="chart-tooltip__row">{formatArea(row.areaHa)}</p>
      <p className="chart-tooltip__row">{formatPercent(row.percent)} of classified area</p>
      <p className="chart-tooltip__row chart-tooltip__muted">NDVI {row.ndviRange}</p>
    </div>
  )
}

/**
 * Area per vegetation class as a horizontal bar chart.
 *
 * Bars are drawn in each class's own palette colour so the chart, the map raster
 * and the summary table are all colour-consistent - the same green in all three
 * always means the same NDVI band.
 *
 * Area (hectares) is plotted rather than percentage: hectares are what a grower
 * acts on, and they stay meaningful when part of the field is cloud-masked.
 */
export function HealthClassChart({ classes, height = 220 }: HealthClassChartProps) {
  const rows: ClassRow[] = classes.map((entry) => ({
    label: entry.label,
    color: entry.color,
    areaHa: Number(entry.area_ha.toFixed(3)),
    percent: entry.percent_of_valid,
    ndviRange: formatNDVIRange(entry.ndvi_min, entry.ndvi_max),
  }))

  const hasArea = rows.some((row) => row.areaHa > 0)
  if (!hasArea) {
    return <p className="hint">No classified area to chart — no cloud-free pixels were available.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
        <XAxis
          type="number"
          tick={{ fontSize: 11 }}
          stroke="#8a9099"
          label={{ value: 'hectares', position: 'insideBottomRight', offset: -2, fontSize: 11 }}
        />
        <YAxis
          type="category"
          dataKey="label"
          width={124}
          tick={{ fontSize: 11 }}
          stroke="#8a9099"
        />
        <Tooltip content={ClassTooltip} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        <Bar dataKey="areaHa" radius={[0, 3, 3, 0]} isAnimationActive={false}>
          {rows.map((row) => (
            <Cell key={row.label} fill={row.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
