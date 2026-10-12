import { Callout } from '@/components/common/Callout'
import type { ConfigResponse, NDVIStatistics } from '@/types/api'

interface ThresholdEditorProps {
  /** Four ascending NDVI boundaries. */
  thresholds: number[]
  isCustom: boolean
  onChange: (thresholds: number[], isCustom: boolean) => void
  config: ConfigResponse | null
  /** Statistics from the last snapshot, enabling relative zoning. */
  statistics: NDVIStatistics | null
  /** Class names in ascending NDVI order, from the server config. */
  classLabels: string[]
}

/** Validate a candidate threshold set the same way the backend does. */
function validate(thresholds: number[]): string | null {
  if (thresholds.length !== 4) return 'Exactly four boundaries are required.'
  for (const value of thresholds) {
    if (!Number.isFinite(value)) return 'All boundaries must be numbers.'
    if (value < -1 || value > 1) return 'NDVI boundaries must lie between −1 and 1.'
  }
  for (let index = 1; index < thresholds.length; index += 1) {
    const previous = thresholds[index - 1]
    const current = thresholds[index]
    if (previous === undefined || current === undefined) return 'All boundaries must be numbers.'
    if (current <= previous) return 'Boundaries must be strictly ascending.'
  }
  return null
}

/**
 * Relative class boundaries derived from this field's own NDVI distribution.
 *
 * This is the "relative zoning" approach: instead of asking whether the crop is
 * healthy in absolute terms - which no fixed NDVI number can answer without
 * local calibration - it asks which parts of *this* field are doing worse than
 * the rest of it right now. That question needs no calibration and is often the
 * more actionable one for scouting.
 */
function relativeThresholds(statistics: NDVIStatistics): number[] | null {
  const { p10, median, p90 } = statistics
  if (p10 === null || median === null || p90 === null) return null
  if (!(p10 < median && median < p90)) return null

  const boundaries = [p10, p10 + (median - p10) / 2, median, p90].map(
    (value) => Math.round(value * 1000) / 1000,
  )
  return validate(boundaries) === null ? boundaries : null
}

/**
 * Editor for the five-class NDVI thresholds.
 *
 * The prominent caution here is not boilerplate. Fixed NDVI cut-offs are the
 * single easiest way to draw a wrong conclusion from this tool: the same wheat
 * field reads 0.35 at tillering and 0.85 at booting, so a "Low" verdict may
 * simply mean "early in the season". The editor exists so these can be
 * calibrated, and the copy says what calibration requires.
 */
export function ThresholdEditor({
  thresholds,
  isCustom,
  onChange,
  config,
  statistics,
  classLabels,
}: ThresholdEditorProps) {
  const error = validate(thresholds)
  const serverDefaults = config?.default_ndvi_class_thresholds ?? null
  const relative = statistics ? relativeThresholds(statistics) : null

  const updateOne = (index: number, raw: string) => {
    const next = [...thresholds]
    next[index] = Number(raw)
    onChange(next, true)
  }

  return (
    <div className="stack">
      <Callout variant="caution" title="These thresholds are conventions, not measurements">
        <p>
          NDVI class boundaries are not universal. They shift with crop type, growth stage, planting
          density, soil background, region and season. Treat the defaults as a starting point for
          <em> relative</em> comparison within one field, and calibrate them against ground
          observations before using them to make decisions.
        </p>
      </Callout>

      <div className="threshold-grid">
        {thresholds.map((value, index) => {
          const below = classLabels[index] ?? `Class ${index + 1}`
          const above = classLabels[index + 1] ?? `Class ${index + 2}`
          return (
            // Index is the identity here: these are four fixed, ordered slots,
            // not a reorderable list.
            <label className="threshold" key={index}>
              <span className="threshold__label">
                {below} → {above}
              </span>
              <input
                type="number"
                min={-1}
                max={1}
                step={0.01}
                value={value}
                onChange={(event) => updateOne(index, event.target.value)}
              />
            </label>
          )
        })}
      </div>

      {error ? <p className="field__error">{error}</p> : null}

      <div className="chip-row">
        {serverDefaults ? (
          <button
            type="button"
            className="chip"
            disabled={!isCustom}
            onClick={() => onChange([...serverDefaults], false)}
          >
            Reset to server defaults
          </button>
        ) : null}
        <button
          type="button"
          className="chip"
          disabled={relative === null}
          title={
            relative === null
              ? 'Run a snapshot analysis first — this needs the field’s NDVI percentiles.'
              : 'Set boundaries from this field’s own p10 / median / p90'
          }
          onClick={() => {
            if (relative) onChange(relative, true)
          }}
        >
          Derive from this field’s distribution
        </button>
      </div>

      <p className="field__hint">
        {isCustom
          ? 'Custom thresholds. The server will report thresholds_source = "request".'
          : 'Using the server defaults. The server will report thresholds_source = "server_default".'}
      </p>

      <p className="field__hint">
        “Derive from this field’s distribution” splits the field by its own 10th percentile, median
        and 90th percentile. The classes then mean “worse than the rest of this field”, not “healthy”
        or “unhealthy” in absolute terms — which is a weaker claim, and a much safer one.
      </p>
    </div>
  )
}
