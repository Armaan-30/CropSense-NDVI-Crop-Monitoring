import { StatTile } from '@/components/common/StatTile'
import { Callout } from '@/components/common/Callout'
import { formatArea, formatFraction, formatNDVI, formatNDVIDelta, formatPercent } from '@/utils/format'
import type { ChangeStatistics, NDVIStatistics } from '@/types/api'

interface ChangeSummaryPanelProps {
  change: ChangeStatistics
  baseline: NDVIStatistics
  recent: NDVIStatistics
}

/** Comparable coverage below this makes the change statistics unreliable. */
const LOW_COMPARABLE = 0.5

/**
 * NDVI difference between the two periods.
 *
 * Everything here is restricted to the *comparable area* - pixels that were
 * cloud-free in both periods. A pixel with data in only one period has no
 * difference to report, and counting it as "no change" would bias the result
 * toward zero exactly where the data is worst.
 */
export function ChangeSummaryPanel({ change, baseline, recent }: ChangeSummaryPanelProps) {
  const meanShift =
    baseline.mean !== null && recent.mean !== null ? recent.mean - baseline.mean : null
  const lowComparable =
    change.comparable_area_fraction !== null && change.comparable_area_fraction < LOW_COMPARABLE
  const declining = change.mean_change !== null && change.mean_change < 0

  return (
    <div className="stack">
      <div className="stat-grid">
        <StatTile
          label="Mean NDVI change"
          value={formatNDVIDelta(change.mean_change)}
          hint="Per-pixel difference, recent − baseline"
          tone={declining ? 'warn' : 'default'}
        />
        <StatTile label="Median change" value={formatNDVIDelta(change.median_change)} />
        <StatTile
          label="Largest decrease"
          value={formatNDVIDelta(change.min_change)}
          hint="Single most negative pixel"
        />
        <StatTile
          label="Largest increase"
          value={formatNDVIDelta(change.max_change)}
          hint="Single most positive pixel"
        />
        <StatTile label="Std. deviation of change" value={formatNDVI(change.std_dev_change)} />
        <StatTile
          label="Comparable area"
          value={formatArea(change.comparable_area_ha)}
          hint={`${formatFraction(change.comparable_area_fraction)} of the AOI had data in both periods`}
          tone={lowComparable ? 'warn' : 'default'}
        />
        <StatTile
          label={`Declined by ≥ ${change.decline_threshold.toFixed(2)}`}
          value={formatArea(change.declined_area_ha)}
          hint={`${formatPercent(change.declined_percent_of_comparable)} of comparable area`}
          tone={
            change.declined_percent_of_comparable !== null &&
            change.declined_percent_of_comparable > 10
              ? 'warn'
              : 'default'
          }
        />
        <StatTile
          label={`Improved by ≥ ${change.decline_threshold.toFixed(2)}`}
          value={formatArea(change.improved_area_ha)}
          hint={`${formatPercent(change.improved_percent_of_comparable)} of comparable area`}
        />
      </div>

      <dl className="kv">
        <dt>Baseline field mean</dt>
        <dd>{formatNDVI(baseline.mean)}</dd>
        <dt>Recent field mean</dt>
        <dd>{formatNDVI(recent.mean)}</dd>
        <dt>Shift in field mean</dt>
        <dd>{formatNDVIDelta(meanShift)}</dd>
      </dl>

      <p className="hint">
        The shift in field mean and the mean per-pixel change need not agree: the field means are
        computed over whatever was cloud-free in each period separately, while the per-pixel change
        uses only the area common to both.
      </p>

      {lowComparable ? (
        <Callout variant="warning" title="Small comparable area">
          Only {formatFraction(change.comparable_area_fraction)} of the field had cloud-free data in
          both periods, so this comparison covers a minority of it. The declined and improved areas
          are lower bounds — the rest of the field is unmeasured, not unchanged.
        </Callout>
      ) : null}

      <Callout variant="caution" title="A decline is a signal to investigate, not a diagnosis">
        <p>
          An NDVI drop means less vigorous vegetation than before. Harvest, cutting, senescence,
          irrigation changes, soil moisture, a different sun angle or residual cloud and haze all
          produce the same signature as crop stress. Disease, pests and nutrient deficiency cannot be
          distinguished from one another — or from a normal management event — using NDVI alone.
          Treat flagged areas as scouting targets and confirm in the field.
        </p>
      </Callout>
    </div>
  )
}
