import type { ReactNode } from 'react'

interface EmptyStateProps {
  title: string
  children?: ReactNode
}

/** Placeholder shown before a panel has anything to display. */
export function EmptyState({ title, children }: EmptyStateProps) {
  return (
    <div className="state state--empty">
      <div className="state__text">
        <p className="state__title">{title}</p>
        {children ? <div className="state__detail">{children}</div> : null}
      </div>
    </div>
  )
}
