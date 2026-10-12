import type { MapLayer } from '@/types/api'

interface LayerLegendProps {
  layer: MapLayer
}

/**
 * Legend for the active map layer.
 *
 * Two renderings, chosen by whether the backend supplied a `value_range`:
 *
 * - **Continuous** (NDVI, NDVI change) - a gradient bar built from the palette
 *   stops with numeric end labels. Nine discrete swatches would imply nine
 *   classes where there is really a stretched ramp.
 * - **Categorical** (health classes, potential stress) - one labelled swatch per
 *   class, showing the exact NDVI bounds that produced it.
 */
export function LayerLegend({ layer }: LayerLegendProps) {
  if (layer.legend.length === 0) {
    return (
      <div className="legend">
        <p className="legend__title">{layer.name}</p>
        <p className="legend__note">Natural-colour imagery — no value scale.</p>
      </div>
    )
  }

  const isContinuous = layer.value_range !== null && layer.value_range.length === 2
  const colors = layer.legend.map((stop) => stop.color)

  if (isContinuous && layer.value_range) {
    const [min, max] = layer.value_range
    const mid = min !== undefined && max !== undefined ? (min + max) / 2 : undefined
    return (
      <div className="legend">
        <p className="legend__title">{layer.name}</p>
        <div
          className="legend__ramp"
          style={{ background: `linear-gradient(to right, ${colors.join(', ')})` }}
          role="img"
          aria-label={`Colour ramp from ${min} to ${max}`}
        />
        <div className="legend__scale">
          <span>{min?.toFixed(2)}</span>
          <span>{mid?.toFixed(2)}</span>
          <span>{max?.toFixed(2)}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="legend">
      <p className="legend__title">{layer.name}</p>
      <ul className="legend__list">
        {layer.legend.map((stop) => (
          <li className="legend__item" key={`${stop.label}-${stop.color}`}>
            <span
              className="legend__swatch"
              style={{ backgroundColor: stop.color }}
              aria-hidden="true"
            />
            <span className="legend__label">{stop.label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
