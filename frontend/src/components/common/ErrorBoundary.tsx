import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

/**
 * Last-resort boundary around the dashboard.
 *
 * Leaflet and Recharts both render imperatively against live DOM, and a single
 * bad value can throw during render. Without a boundary that unmounts the whole
 * page to a blank screen, which looks identical to a network failure. This shows
 * the actual message instead, and offers a reload rather than pretending the
 * state is recoverable.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled error in the CropSense UI:', error, info.componentStack)
  }

  override render(): ReactNode {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div className="state state--error" role="alert">
        <p className="state__title">The dashboard hit an unexpected error</p>
        <p className="state__message">{error.message}</p>
        <p className="state__detail">
          The full stack trace is in the browser console. Any analysis results on screen were lost,
          but nothing on the server was changed.
        </p>
        <button type="button" className="button button--secondary" onClick={() => location.reload()}>
          Reload the page
        </button>
      </div>
    )
  }
}
