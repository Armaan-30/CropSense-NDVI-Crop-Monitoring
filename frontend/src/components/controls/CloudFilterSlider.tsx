interface CloudFilterSliderProps {
  /** Scene-level `CLOUDY_PIXEL_PERCENTAGE` cut-off, 0-100. */
  value: number
  onChange: (value: number) => void
}

/**
 * Scene-level cloud-cover filter.
 *
 * This is a *scene* filter, not the per-pixel cloud mask - the distinction
 * trips people up, so the copy says it explicitly. Raising it admits more
 * scenes; the per-pixel mask still removes the cloudy pixels within them. That
 * is usually the right move when a strict setting returns no imagery, at the
 * cost of relying on the mask over a larger fraction of the field.
 */
export function CloudFilterSlider({ value, onChange }: CloudFilterSliderProps) {
  return (
    <label className="field">
      <span className="field__label">
        Maximum scene cloud cover <output>{value.toFixed(0)}%</output>
      </span>
      <input
        type="range"
        min={0}
        max={100}
        step={5}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <p className="field__hint">
        Discards whole Sentinel-2 scenes cloudier than this, before any pixel masking. Raise it if
        you get “no usable imagery”; cloudy pixels are still masked out individually.
      </p>
    </label>
  )
}
