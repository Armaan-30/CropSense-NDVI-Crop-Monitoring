interface StatTileProps {
  label: string
  value: string
  /** Secondary line: units, sample size, or a caveat. */
  hint?: string
  /**
   * Colour cue. Kept deliberately neutral by default - NDVI numbers are not
   * "good" or "bad" without local context, so only use `warn` for genuine data
   * quality problems (e.g. low cloud-free coverage), never for a low NDVI.
   */
  tone?: 'default' | 'warn' | 'muted'
}

/** Single labelled number in a statistics grid. */
export function StatTile({ label, value, hint, tone = 'default' }: StatTileProps) {
  return (
    <div className={`stat stat--${tone}`}>
      <span className="stat__label">{label}</span>
      <span className="stat__value">{value}</span>
      {hint ? <span className="stat__hint">{hint}</span> : null}
    </div>
  )
}
