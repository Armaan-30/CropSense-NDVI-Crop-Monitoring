import { daysBetween, isOrderedRange, recentWindow, today } from '@/utils/dates'
import type { DateRange } from '@/types/api'

interface DateRangeFieldProps {
  label: string
  value: DateRange
  onChange: (range: DateRange) => void
  /** Earliest selectable date, e.g. the start of Sentinel-2 L2A coverage. */
  min: string
  /** Server limit on window length, from `/api/system/config`. */
  maxDays?: number
  /** Quick-pick buttons, in days. Omit to hide them. */
  presets?: number[]
  /** Extra explanation under the inputs. */
  hint?: string
}

/**
 * Start/end date pair with the constraints that actually matter for Sentinel-2.
 *
 * The window is inclusive at both ends, matching the backend. The day count is
 * shown live because window length is the single biggest driver of whether a
 * cloudy period yields any usable imagery at all - a 5-day window over the
 * monsoon will routinely return nothing, and seeing "5 days" makes that obvious.
 */
export function DateRangeField({
  label,
  value,
  onChange,
  min,
  maxDays,
  presets,
  hint,
}: DateRangeFieldProps) {
  const ordered = isOrderedRange(value.start_date, value.end_date)
  const days = ordered ? daysBetween(value.start_date, value.end_date) : 0
  const tooLong = maxDays !== undefined && days > maxDays

  const applyPreset = (windowDays: number) => onChange(recentWindow(windowDays))

  return (
    <fieldset className="field">
      <legend className="field__label">{label}</legend>

      <div className="field__row">
        <label className="field__inline">
          <span>From</span>
          <input
            type="date"
            value={value.start_date}
            min={min}
            max={today()}
            onChange={(event) => onChange({ ...value, start_date: event.target.value })}
          />
        </label>
        <label className="field__inline">
          <span>To</span>
          <input
            type="date"
            value={value.end_date}
            min={min}
            max={today()}
            onChange={(event) => onChange({ ...value, end_date: event.target.value })}
          />
        </label>
      </div>

      {presets && presets.length > 0 ? (
        <div className="chip-row">
          {presets.map((windowDays) => (
            <button
              key={windowDays}
              type="button"
              className="chip"
              onClick={() => applyPreset(windowDays)}
            >
              Last {windowDays} days
            </button>
          ))}
        </div>
      ) : null}

      {!ordered ? (
        <p className="field__error">The end date must be on or after the start date.</p>
      ) : tooLong ? (
        <p className="field__error">
          {days} days exceeds the server limit of {maxDays} days.
        </p>
      ) : (
        <p className="field__hint">
          {days} day{days === 1 ? '' : 's'} selected
          {days < 10 ? ' — short windows often contain no cloud-free overpass.' : '.'}
        </p>
      )}

      {hint ? <p className="field__hint">{hint}</p> : null}
    </fieldset>
  )
}
