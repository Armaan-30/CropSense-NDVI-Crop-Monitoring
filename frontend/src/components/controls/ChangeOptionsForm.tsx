import { Callout } from '@/components/common/Callout'
import type { AnalysisSettings } from '@/types/settings'

interface ChangeOptionsFormProps {
  settings: AnalysisSettings
  onChange: (patch: Partial<AnalysisSettings>) => void
  /** Server default, for the reset hint. */
  serverDefault: number | null
}

/**
 * NDVI drop that counts as a decline.
 *
 * Below roughly 0.05 the threshold sits inside the noise floor: sun-target-sensor
 * geometry, atmospheric correction residuals and thin haze can move NDVI by that
 * much between two dates with nothing happening on the ground. The slider allows
 * lower values because a smoothed monthly composite is quieter than two single
 * scenes, but the copy says what is being traded.
 */
const NOISE_FLOOR = 0.05

export function ChangeOptionsForm({ settings, onChange, serverDefault }: ChangeOptionsFormProps) {
  const belowNoiseFloor = settings.declineThreshold < NOISE_FLOOR

  return (
    <div className="stack">
      <label className="field">
        <span className="field__label">
          Decline threshold: {settings.declineThreshold.toFixed(2)} NDVI
        </span>
        <input
          type="range"
          min={0.01}
          max={0.5}
          step={0.01}
          value={settings.declineThreshold}
          onChange={(event) => onChange({ declineThreshold: Number(event.target.value) })}
        />
        <p className="field__hint">
          A pixel is reported as declined when its NDVI fell by at least this much between the two
          periods, and as improved when it rose by at least this much.
          {serverDefault !== null ? ` The server default is ${serverDefault.toFixed(2)}.` : ''}
        </p>
      </label>

      {belowNoiseFloor ? (
        <Callout variant="warning" title="This threshold is inside the noise">
          Differences smaller than about {NOISE_FLOOR.toFixed(2)} NDVI can be produced by view
          geometry, atmospheric correction and thin haze alone. At this setting a large part of the
          flagged area is likely to be measurement noise rather than a change in the crop.
        </Callout>
      ) : null}
    </div>
  )
}
