import { Callout } from '@/components/common/Callout'
import { formatArea, formatCount, formatNDVIRange, formatPercent } from '@/utils/format'
import type { HealthSummary } from '@/types/api'

interface HealthSummaryPanelProps {
  health: HealthSummary
  /** Suppress the calibration note when a parent view already shows it once. */
  hideCalibrationNote?: boolean
}

/**
 * Per-class area and share of the classified area.
 *
 * Percentages are of the *cloud-free classified area*, not of the AOI. Those two
 * differ whenever cloud masking removed pixels, and conflating them is how a
 * field that is 60% obscured ends up reported as 60% non-vegetated.
 */
export function HealthSummaryPanel({ health, hideCalibrationNote }: HealthSummaryPanelProps) {
  const dominant = health.classes.find((entry) => entry.key === health.dominant_class)
  const sourceLabel =
    health.thresholds_source === 'request' ? 'custom (from this request)' : 'server default'

  return (
    <div className="stack">
      {/* A single stacked bar reads faster than five numbers when the question is
          "how is this field split up?". The table below it carries the detail. */}
      <div
        className="class-bar"
        role="img"
        aria-label={health.classes
          .map((entry) => `${entry.label} ${entry.percent_of_valid.toFixed(1)}%`)
          .join(', ')}
      >
        {health.classes
          .filter((entry) => entry.percent_of_valid > 0)
          .map((entry) => (
            <div
              key={entry.key}
              className="class-bar__segment"
              style={{ width: `${entry.percent_of_valid}%`, backgroundColor: entry.color }}
              title={`${entry.label}: ${formatPercent(entry.percent_of_valid)}`}
            />
          ))}
      </div>

      <table className="table">
        <thead>
          <tr>
            <th scope="col">Class</th>
            <th scope="col">NDVI range</th>
            <th scope="col" className="table__num">
              Area
            </th>
            <th scope="col" className="table__num">
              Share
            </th>
            <th scope="col" className="table__num">
              Pixels
            </th>
          </tr>
        </thead>
        <tbody>
          {health.classes.map((entry) => (
            <tr key={entry.key} className={entry.key === health.dominant_class ? 'is-dominant' : ''}>
              <th scope="row">
                <span className="swatch" style={{ backgroundColor: entry.color }} aria-hidden="true" />
                {entry.label}
              </th>
              <td className="table__mono">{formatNDVIRange(entry.ndvi_min, entry.ndvi_max)}</td>
              <td className="table__num">{formatArea(entry.area_ha)}</td>
              <td className="table__num">{formatPercent(entry.percent_of_valid)}</td>
              <td className="table__num">{formatCount(entry.pixel_count)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <dl className="kv">
        <dt>Classified area</dt>
        <dd>
          {formatArea(health.classified_area_ha)} <small>(cloud-free pixels only)</small>
        </dd>

        <dt>Dominant class</dt>
        <dd>
          {dominant ? (
            <>
              <span className="swatch" style={{ backgroundColor: dominant.color }} aria-hidden="true" />
              {dominant.label} — {formatPercent(dominant.percent_of_valid)}
            </>
          ) : (
            'No class could be determined'
          )}
        </dd>

        <dt>Thresholds used</dt>
        <dd className="table__mono">
          {health.thresholds.map((value) => value.toFixed(2)).join(' / ')} <small>({sourceLabel})</small>
        </dd>
      </dl>

      {hideCalibrationNote ? null : (
        <Callout variant="caution" title="Calibration">
          {health.calibration_note}
        </Callout>
      )}
    </div>
  )
}
