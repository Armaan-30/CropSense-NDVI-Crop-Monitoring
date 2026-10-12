import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { Dashboard } from '@/pages/Dashboard'

/** Application root. Routing is not needed - the dashboard is the whole app. */
export function App() {
  return (
    <ErrorBoundary>
      <Dashboard />
    </ErrorBoundary>
  )
}
