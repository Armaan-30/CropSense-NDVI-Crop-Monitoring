import type { ReactNode } from 'react'

interface PanelProps {
  title: string
  /** Short clarifying line under the title. */
  subtitle?: string
  /** Right-aligned controls in the panel header. */
  actions?: ReactNode
  children: ReactNode
  /** Extra class names, e.g. for grid placement. */
  className?: string
  /** Renders the panel with no body padding, for tables and maps. */
  flush?: boolean
}

/**
 * Standard titled container.
 *
 * Every result group is wrapped in one of these so headings, spacing and
 * borders stay consistent without each panel re-inventing them.
 */
export function Panel({ title, subtitle, actions, children, className, flush }: PanelProps) {
  return (
    <section className={`panel${className ? ` ${className}` : ''}`}>
      <header className="panel__header">
        <div className="panel__titles">
          <h2 className="panel__title">{title}</h2>
          {subtitle ? <p className="panel__subtitle">{subtitle}</p> : null}
        </div>
        {actions ? <div className="panel__actions">{actions}</div> : null}
      </header>
      <div className={`panel__body${flush ? ' panel__body--flush' : ''}`}>{children}</div>
    </section>
  )
}
