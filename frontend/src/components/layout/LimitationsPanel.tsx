import { useState } from 'react'
import { Callout } from '@/components/common/Callout'
import type { ConfigResponse } from '@/types/api'

interface LimitationsPanelProps {
  config: ConfigResponse | null
}

/**
 * The backend's own statement of what this tool can and cannot support.
 *
 * Rendered from `/api/system/config` rather than written into the UI, so the
 * limitations shown always match the processing that actually ran. Collapsed by
 * default but never hidden: NDVI is easy to over-read, and the list is the
 * difference between "this field needs looking at" and "this field is diseased".
 */
export function LimitationsPanel({ config }: LimitationsPanelProps) {
  const [open, setOpen] = useState(false)

  if (!config) return null

  return (
    <div className="stack stack--tight">
      <Callout variant="caution" title="NDVI measures vigour, not cause">
        NDVI responds to green canopy density and condition. It cannot identify a disease, a pest or a
        nutrient deficiency, and a low or falling value has many ordinary explanations — growth stage,
        harvest, irrigation, soil background, haze. Use it to decide where to look, then confirm on
        the ground.
      </Callout>

      <button type="button" className="chip" onClick={() => setOpen((value) => !value)}>
        {open ? 'Hide details' : 'Assumptions, bands and limitations'}
      </button>

      {open ? (
        <div className="stack stack--tight">
          <dl className="kv">
            <dt>Collection</dt>
            <dd className="table__mono">{config.collection_id}</dd>
            <dt>Bands</dt>
            <dd className="table__mono">
              Red {config.band_red} · NIR {config.band_nir}
            </dd>
            <dt>Formula</dt>
            <dd className="table__mono">NDVI = (NIR − Red) / (NIR + Red)</dd>
            <dt>Default scale</dt>
            <dd>{config.default_scale_m} m</dd>
            <dt>Max AOI</dt>
            <dd>{config.max_aoi_area_km2} km²</dd>
            <dt>Max date range</dt>
            <dd>{config.max_date_range_days} days</dd>
          </dl>

          {config.limitations.length > 0 ? (
            <>
              <p className="field__label">Known limitations</p>
              <ul className="advice">
                {config.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          ) : null}

          <p className="hint">{config.calibration_note}</p>
        </div>
      ) : null}
    </div>
  )
}
