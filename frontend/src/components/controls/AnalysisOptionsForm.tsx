import { CLOUD_MASK_METHODS, COMPOSITE_METHODS } from '@/types/api'
import { cloudMaskLabel, compositeLabel } from '@/utils/format'
import type { AnalysisSettings } from '@/types/settings'
import type { ConfigResponse } from '@/types/api'

interface AnalysisOptionsFormProps {
  settings: AnalysisSettings
  onChange: (patch: Partial<AnalysisSettings>) => void
  /** Server config, for showing what the defaults actually are. */
  config: ConfigResponse | null
}

/** Analysis scales offered. 10 m is Sentinel-2 native for B4 and B8. */
const SCALE_OPTIONS = [10, 20, 30, 60, 100]

/**
 * Processing options: cloud mask, compositing, scale and AOI buffer.
 *
 * Each control carries a one-line explanation of the trade-off rather than just
 * a label. These choices change the numbers materially - a `greenest` composite
 * biases NDVI upward, and a 100 m scale smooths away exactly the within-field
 * variation someone would be looking for - so the UI says so at the point of
 * choosing.
 */
export function AnalysisOptionsForm({ settings, onChange, config }: AnalysisOptionsFormProps) {
  return (
    <div className="stack">
      <label className="field">
        <span className="field__label">Cloud / shadow mask</span>
        <select
          value={settings.cloudMaskMethod}
          onChange={(event) =>
            onChange({ cloudMaskMethod: event.target.value as AnalysisSettings['cloudMaskMethod'] })
          }
        >
          {CLOUD_MASK_METHODS.map((method) => (
            <option key={method} value={method}>
              {cloudMaskLabel(method)}
              {config?.default_cloud_mask_method === method ? ' (server default)' : ''}
            </option>
          ))}
        </select>
        <p className="field__hint">
          Cloud Score+ is the most reliable general-purpose mask but only covers dates from 27 June
          2017. “No pixel masking” is for diagnostics only — cloud will inflate or destroy NDVI.
        </p>
      </label>

      {settings.cloudMaskMethod === 'cs_plus' ? (
        <label className="field">
          <span className="field__label">
            Cloud Score+ threshold <output>{settings.cloudScorePlusThreshold.toFixed(2)}</output>
          </span>
          <input
            type="range"
            min={0.1}
            max={0.95}
            step={0.05}
            value={settings.cloudScorePlusThreshold}
            onChange={(event) =>
              onChange({ cloudScorePlusThreshold: Number(event.target.value) })
            }
          />
          <p className="field__hint">
            Minimum “clear” score a pixel must reach to be kept. Higher is stricter: cleaner pixels,
            but fewer of them, so watch the cloud-free coverage figure in the results.
          </p>
        </label>
      ) : null}

      <label className="field">
        <span className="field__label">Compositing method</span>
        <select
          value={settings.compositeMethod}
          onChange={(event) =>
            onChange({ compositeMethod: event.target.value as AnalysisSettings['compositeMethod'] })
          }
        >
          {COMPOSITE_METHODS.map((method) => (
            <option key={method} value={method}>
              {compositeLabel(method)}
              {config?.default_composite_method === method ? ' (server default)' : ''}
            </option>
          ))}
        </select>
        <p className="field__hint">
          How several scenes become one image. Median is robust to leftover cloud. “Greenest pixel”
          is biased high and is a poor basis for judging stress. “Most recent pixel” best represents
          current state.
        </p>
      </label>

      <label className="field">
        <span className="field__label">Analysis scale</span>
        <select
          value={settings.scaleM}
          onChange={(event) => onChange({ scaleM: Number(event.target.value) })}
        >
          {SCALE_OPTIONS.map((scale) => (
            <option key={scale} value={scale}>
              {scale} m{scale === 10 ? ' (Sentinel-2 native)' : ''}
              {config?.default_scale_m === scale ? ' — server default' : ''}
            </option>
          ))}
        </select>
        <p className="field__hint">
          Pixel size for statistics and areas. Coarser scales compute much faster on large fields
          but average away within-field variation.
        </p>
      </label>

      <label className="field">
        <span className="field__label">
          AOI buffer <output>{settings.bufferM} m</output>
        </span>
        <input
          type="range"
          min={0}
          max={2000}
          step={25}
          value={settings.bufferM}
          onChange={(event) => onChange({ bufferM: Number(event.target.value) })}
        />
        <p className="field__hint">
          Expands the drawn shape outward. Required for a marker AOI (it becomes the radius); for a
          drawn field, keep it at 0 unless you want to include the surrounding margin — buffering
          pulls in field edges, tracks and hedgerows, which drags the mean NDVI down.
        </p>
      </label>

      <label className="checkbox">
        <input
          type="checkbox"
          checked={settings.includeTrueColor}
          onChange={(event) => onChange({ includeTrueColor: event.target.checked })}
        />
        <span>
          Also request a true-colour (RGB) layer
          <small>Lets you see whether an odd NDVI reading is cloud, shadow or bare soil.</small>
        </span>
      </label>
    </div>
  )
}
