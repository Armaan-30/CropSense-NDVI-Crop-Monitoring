import type { ReactNode } from 'react'

type CalloutVariant = 'info' | 'warning' | 'caution'

interface CalloutProps {
  variant?: CalloutVariant
  title?: string
  children: ReactNode
}

const ICONS: Record<CalloutVariant, string> = {
  info: 'ℹ',
  warning: '⚠',
  caution: '!',
}

/**
 * Inline notice for notes, data-quality warnings and scientific caveats.
 *
 * `caution` is reserved for the interpretation limits that must never be
 * dismissed — chiefly that NDVI measures vegetation vigour and does not
 * identify a cause or diagnose disease.
 */
export function Callout({ variant = 'info', title, children }: CalloutProps) {
  return (
    <div className={`callout callout--${variant}`}>
      <span className="callout__icon" aria-hidden="true">
        {ICONS[variant]}
      </span>
      <div className="callout__content">
        {title ? <p className="callout__title">{title}</p> : null}
        <div className="callout__body">{children}</div>
      </div>
    </div>
  )
}

interface MessageListProps {
  /** `warnings` from any analysis response. Data-quality caveats. */
  warnings?: string[]
  /** `notes` from any analysis response. Method and interpretation notes. */
  notes?: string[]
}

/**
 * Render a response's `warnings` and `notes`.
 *
 * These are not decoration. The backend puts real reliability information here —
 * low cloud-free coverage, single-scene composites, thresholds that were
 * overridden — so every result view shows them.
 */
export function MessageList({ warnings = [], notes = [] }: MessageListProps) {
  if (warnings.length === 0 && notes.length === 0) return null

  return (
    <div className="messages">
      {warnings.length > 0 ? (
        <Callout variant="warning" title="Data-quality warnings">
          <ul className="messages__list">
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Callout>
      ) : null}

      {notes.length > 0 ? (
        <Callout variant="info" title="Method notes">
          <ul className="messages__list">
            {notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </Callout>
      ) : null}
    </div>
  )
}
