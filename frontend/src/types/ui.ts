/** UI-only types that have no backend counterpart. */

/**
 * Which analysis the dashboard is showing.
 *
 * One tab per NDVI endpoint. Results are kept per mode rather than shared, so
 * switching tabs never discards a computation that took 30 seconds.
 */
export type AnalysisMode = 'snapshot' | 'series' | 'compare'

export interface ModeDefinition {
  id: AnalysisMode
  label: string
  /** What this mode answers, in one line. */
  description: string
}

export const ANALYSIS_MODES: readonly ModeDefinition[] = [
  {
    id: 'snapshot',
    label: 'Snapshot',
    description: 'NDVI, statistics and health classes for a single date window.',
  },
  {
    id: 'series',
    label: 'Time series',
    description: 'Mean NDVI over time, with a linear trend.',
  },
  {
    id: 'compare',
    label: 'Compare periods',
    description: 'Difference two windows and screen for potential vegetation stress.',
  },
]
