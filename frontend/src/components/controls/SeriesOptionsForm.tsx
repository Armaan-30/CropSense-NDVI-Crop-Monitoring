import { TEMPORAL_AGGREGATIONS } from '@/types/api'
import { aggregationLabel, formatFraction } from '@/utils/format'
import type { TemporalAggregation } from '@/types/api'
import type { AnalysisSettings } from '@/types/settings'

interface SeriesOptionsFormProps {
  settings: AnalysisSettings
  onChange: (patch: Partial<AnalysisSettings>) => void
}

/** Time-step and coverage controls for the temporal series. */
export function SeriesOptionsForm({ settings, onChange }: SeriesOptionsFormProps) {
  return (
    <div className="stack">
      <label className="field">
        <span className="field__label">Time step</span>
        <select
          value={settings.aggregation}
          onChange={(event) =>
            onChange({ aggregation: event.target.value as TemporalAggregation })
          }
        >
          {TEMPORAL_AGGREGATIONS.map((option) => (
            <option key={option} value={option}>
              {aggregationLabel(option)}
            </option>
          ))}
        </select>
        <p className="field__hint">
          Per scene gives one point per Sentinel-2 overpass — the rawest view, and the noisiest.
          Weekly, fortnightly and monthly composite the scenes inside each period, which fills cloud
          gaps but smooths away short-lived changes.
        </p>
      </label>

      <label className="field">
        <span className="field__label">
          Minimum cloud-free coverage per step: {formatFraction(settings.minValidFraction, 0)}
        </span>
        <input
          type="range"
          min={0}
          max={0.95}
          step={0.05}
          value={settings.minValidFraction}
          onChange={(event) => onChange({ minValidFraction: Number(event.target.value) })}
        />
        <p className="field__hint">
          Time steps with less usable coverage than this are dropped rather than plotted. Set it too
          low and a mean computed from a sliver of the field appears as a real observation; set it
          too high and the series thins out to nothing in a cloudy season. Dropped steps are counted
          in the result.
        </p>
      </label>
    </div>
  )
}
