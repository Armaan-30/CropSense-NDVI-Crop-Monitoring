import { useState } from 'react'
import {
  cloudMaskLabel,
  compositeLabel,
  formatCount,
  formatDate,
  formatPercent,
} from '@/utils/format'
import type { ImagerySummary } from '@/types/api'

interface ImageryProvenancePanelProps {
  imagery: ImagerySummary
  /** Label when two periods are shown side by side, e.g. "Baseline". */
  caption?: string
}

/** Scene ids listed before the list collapses behind a toggle. */
const VISIBLE_SCENES = 4

/**
 * Which satellite scenes produced this result.
 *
 * This panel is the answer to "where did this number come from?". Every statistic
 * elsewhere in the dashboard is a reduction of exactly these scenes under exactly
 * this mask and composite, and without them a mean NDVI is an unfalsifiable
 * claim. Scene ids are shown verbatim so a result can be reproduced in the Earth
 * Engine Code Editor independently of this application.
 */
export function ImageryProvenancePanel({ imagery, caption }: ImageryProvenancePanelProps) {
  const [expanded, setExpanded] = useState(false)
  const scenes = expanded ? imagery.scene_ids : imagery.scene_ids.slice(0, VISIBLE_SCENES)
  const hidden = imagery.scene_ids.length - scenes.length

  return (
    <div className="stack">
      {caption ? <p className="section-caption">{caption}</p> : null}

      <dl className="kv">
        <dt>Collection</dt>
        <dd className="table__mono">{imagery.collection_id}</dd>

        <dt>Scenes used</dt>
        <dd>
          {formatCount(imagery.scene_count)}
          {imagery.scene_count === 1 ? ' scene' : ' scenes'}
        </dd>

        <dt>Requested window</dt>
        <dd>
          {formatDate(imagery.requested_range.start_date)} –{' '}
          {formatDate(imagery.requested_range.end_date)}
        </dd>

        <dt>Actual acquisition span</dt>
        <dd>
          {imagery.first_scene_date && imagery.last_scene_date ? (
            imagery.first_scene_date === imagery.last_scene_date ? (
              formatDate(imagery.first_scene_date)
            ) : (
              <>
                {formatDate(imagery.first_scene_date)} – {formatDate(imagery.last_scene_date)}
              </>
            )
          ) : (
            'No scenes'
          )}
        </dd>

        <dt>Scene cloud filter</dt>
        <dd>
          ≤ {imagery.cloud_threshold_percent}% CLOUDY_PIXEL_PERCENTAGE
          {imagery.mean_scene_cloud_percent !== null ? (
            <small> · mean of selected scenes {formatPercent(imagery.mean_scene_cloud_percent)}</small>
          ) : null}
        </dd>

        <dt>Pixel mask</dt>
        <dd>{cloudMaskLabel(imagery.cloud_mask_method)}</dd>

        <dt>Composite</dt>
        <dd>{compositeLabel(imagery.composite_method)}</dd>
      </dl>

      {imagery.scene_ids.length > 0 ? (
        <div className="stack stack--tight">
          <p className="field__label">Scene ids</p>
          <ul className="scene-list">
            {scenes.map((id, index) => (
              <li key={id} className="table__mono">
                {id}
                {imagery.scene_dates[index] ? (
                  <small> · {formatDate(imagery.scene_dates[index])}</small>
                ) : null}
              </li>
            ))}
          </ul>
          {hidden > 0 || expanded ? (
            <button type="button" className="chip" onClick={() => setExpanded((open) => !open)}>
              {expanded ? 'Show fewer' : `Show ${hidden} more`}
            </button>
          ) : null}
        </div>
      ) : null}

      <p className="hint">
        A composite is not a photograph of one moment. With {formatCount(imagery.scene_count)} scenes
        combined by {compositeLabel(imagery.composite_method).toLowerCase()}, each pixel may come from
        a different acquisition date within the window above.
      </p>
    </div>
  )
}
