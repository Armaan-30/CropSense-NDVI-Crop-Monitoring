import { StatTile } from '@/components/common/StatTile'
import { Callout } from '@/components/common/Callout'
import { formatCount, formatNDVI, formatNDVIDelta } from '@/utils/format'
import type { TrendSummary } from '@/types/api'

interface TrendPanelProps {
  trend: TrendSummary | null
  /** Time steps the server dropped for insufficient cloud-free coverage. */
  excludedPointCount: number
}

/** Fits weaker than this explain little of the variation. */
const WEAK_FIT = 0.3

function directionLabel(direction: string): string {
  switch (direction) {
    case 'increasing':
      return 'Increasing'
    case 'decreasing':
      return 'Decreasing'
    case 'stable':
      return 'Stable'
    case 'insufficient_data':
      return 'Not enough data'
    default:
      return direction
  }
}

/**
 * Linear trend over the series.
 *
 * R² is shown next to the slope rather than tucked away, because a slope without
 * it is close to meaningless here: a crop's NDVI curve rises and then falls, so a
 * straight line fitted across a whole season can report "stable" for a field that
 * grew vigorously and was then harvested. A low R² is the signal to read the
 * chart instead of the number.
 */
export function TrendPanel({ trend, excludedPointCount }: TrendPanelProps) {
  if (!trend) {
    return <p className="hint">No trend was computed for this series.</p>
  }

  const weakFit = trend.r_squared !== null && trend.r_squared < WEAK_FIT
  const insufficient = trend.direction === 'insufficient_data'

  return (
    <div className="stack">
      <div className="stat-grid">
        <StatTile
          label="Direction"
          value={directionLabel(trend.direction)}
          hint="From the sign of the fitted slope"
          tone={insufficient ? 'muted' : 'default'}
        />
        <StatTile
          label="Slope"
          value={
            trend.slope_ndvi_per_30_days !== null
              ? `${formatNDVIDelta(trend.slope_ndvi_per_30_days)} / 30 d`
              : '—'
          }
        />
        <StatTile
          label="R²"
          value={trend.r_squared !== null ? trend.r_squared.toFixed(2) : '—'}
          hint="Share of variation explained by a straight line"
          tone={weakFit ? 'warn' : 'default'}
        />
        <StatTile
          label="Observations used"
          value={formatCount(trend.n_points)}
          hint={
            excludedPointCount > 0
              ? `${formatCount(excludedPointCount)} step(s) excluded for low coverage`
              : 'All available time steps'
          }
        />
        <StatTile label="First value" value={formatNDVI(trend.first_value)} />
        <StatTile label="Last value" value={formatNDVI(trend.last_value)} />
        <StatTile
          label="Net change"
          value={formatNDVIDelta(trend.absolute_change)}
          hint="Last minus first observation, not the fit"
        />
      </div>

      <Callout variant="info" title="How to read this">
        {trend.interpretation}
      </Callout>

      {weakFit && !insufficient ? (
        <Callout variant="warning" title="The straight line fits poorly">
          R² is {trend.r_squared?.toFixed(2)}, so most of the variation is not linear. This is normal
          across a growing season — NDVI rises and then falls. Read the shape of the chart rather
          than the slope.
        </Callout>
      ) : null}
    </div>
  )
}
