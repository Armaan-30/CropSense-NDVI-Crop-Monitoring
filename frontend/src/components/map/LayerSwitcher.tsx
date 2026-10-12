import type { MapLayer } from '@/types/api'

interface LayerSwitcherProps {
  layers: MapLayer[]
  activeLayerId: string | null
  onActiveLayerChange: (layerId: string | null) => void
  /** Overlay opacity, 0-1. */
  opacity: number
  onOpacityChange: (opacity: number) => void
}

/**
 * Chooses which analysis raster is drawn over the basemap.
 *
 * One overlay at a time, by design: two semi-transparent thematic rasters
 * stacked on each other produce colours that mean nothing. `true_color` is
 * excluded here because the map's own layer control offers it as a toggle that
 * sits *underneath* the thematic overlay, which is what makes it useful as a
 * visual cross-check.
 */
export function LayerSwitcher({
  layers,
  activeLayerId,
  onActiveLayerChange,
  opacity,
  onOpacityChange,
}: LayerSwitcherProps) {
  const thematic = layers.filter((layer) => layer.id !== 'true_color')

  if (thematic.length === 0) {
    return <p className="hint">Run an analysis to get map layers.</p>
  }

  const active = thematic.find((layer) => layer.id === activeLayerId) ?? null

  return (
    <div className="layer-switcher">
      <fieldset className="field">
        <legend className="field__label">Map overlay</legend>
        <div className="radio-list">
          {thematic.map((layer) => (
            <label className="radio" key={layer.id}>
              <input
                type="radio"
                name="active-layer"
                value={layer.id}
                checked={activeLayerId === layer.id}
                onChange={() => onActiveLayerChange(layer.id)}
              />
              <span>{layer.name}</span>
            </label>
          ))}
          <label className="radio">
            <input
              type="radio"
              name="active-layer"
              value=""
              checked={activeLayerId === null}
              onChange={() => onActiveLayerChange(null)}
            />
            <span>None (basemap only)</span>
          </label>
        </div>
      </fieldset>

      {active ? <p className="hint">{active.description}</p> : null}

      <label className="field">
        <span className="field__label">
          Overlay opacity <output>{Math.round(opacity * 100)}%</output>
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={opacity}
          disabled={activeLayerId === null}
          onChange={(event) => onOpacityChange(Number(event.target.value))}
        />
      </label>
    </div>
  )
}
