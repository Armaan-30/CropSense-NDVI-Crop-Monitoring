import { StatTile } from '@/components/common/StatTile'
import { Callout } from '@/components/common/Callout'
import { formatCount, formatFraction, formatNDVI } from '@/utils/format'
import type { NDVIStatistics } from '@/types/api'

interface StatisticsPanelProps {
  statistics: NDVIStatistics
  /** Heading shown above the grid, e.g. "Baseline period". */
  caption?: string
}

/** Coverage below this makes the field-level mean unrepresentative. */
const LOW_COVERAGE = 0.5

/**
 * Zonal NDVI statistics for the AOI.
 *
 * Cloud-free coverage is shown as prominently as the mean, on purpose. A mean of
 * 0.71 computed from 8% of a field is not a field mean, and there is nothing in
 * the number itself that says so - the coverage figure is the only thing that
 * distinguishes a reliable result from a misleading one.
 */
export function StatisticsPanel({ statistics, caption }: StatisticsPanelProps) {
  const coverage = statistics.valid_pixel_fraction
  const lowCoverage = coverage !== null && coverage < LOW_COVERAGE
  const spread =
    statistics.p90 !== null && statistics.p10 !== null ? statistics.p90 - statistics.p10 : null

  return (
    <div className="stack">
      {caption ? <p className="section-caption">{caption}</p> : null}

      <div className="stat-grid">
        <StatTile label="Mean NDVI" value={formatNDVI(statistics.mean)} hint="Cloud-free pixels only" />
        <StatTile label="Median" value={formatNDVI(statistics.median)} />
        <StatTile label="Minimum" value={formatNDVI(statistics.min)} />
        <StatTile label="Maximum" value={formatNDVI(statistics.max)} />
        <StatTile
          label="Std. deviation"
          value={formatNDVI(statistics.std_dev)}
          hint="Within-field variability"
        />
        <StatTile
          label="10th–90th percentile"
          value={
            statistics.p10 !== null && statistics.p90 !== null
              ? `${formatNDVI(statistics.p10, 2)} – ${formatNDVI(statistics.p90, 2)}`
              : '—'
          }
          hint={spread !== null ? `spread ${formatNDVI(spread, 2)}` : undefined}
        />
        <StatTile
          label="Cloud-free coverage"
          value={formatFraction(coverage)}
          hint={`${formatCount(statistics.valid_pixel_count)} of ${formatCount(
            statistics.total_pixel_count,
          )} pixels`}
          tone={lowCoverage ? 'warn' : 'default'}
        />
        <StatTile
          label="Analysis scale"
          value={statistics.scale_m !== null ? `${statistics.scale_m} m` : '—'}
          tone="muted"
        />
      </div>

      {lowCoverage ? (
        <Callout variant="warning" title="Low cloud-free coverage">
          Only {formatFraction(coverage)} of the area had usable pixels, so these statistics describe
          a fraction of the field rather than the whole of it. Widen the date range or raise the
          scene cloud limit before drawing conclusions.
        </Callout>
      ) : null}

      {statistics.mean === null ? (
        <Callout variant="warning" title="No cloud-free pixels">
          Earth Engine returned no valid pixels for this area and window. This is a missing
          measurement, not a low NDVI value.
        </Callout>
      ) : null}
    </div>
  )
}
