import { ANALYSIS_MODES } from '@/types/ui'
import type { AnalysisMode } from '@/types/ui'

interface ModeTabsProps {
  mode: AnalysisMode
  onChange: (mode: AnalysisMode) => void
}

/** Tab strip selecting which analysis endpoint the dashboard is driving. */
export function ModeTabs({ mode, onChange }: ModeTabsProps) {
  const active = ANALYSIS_MODES.find((definition) => definition.id === mode)

  return (
    <div className="tabs">
      <div className="tabs__strip" role="tablist" aria-label="Analysis mode">
        {ANALYSIS_MODES.map((definition) => (
          <button
            key={definition.id}
            type="button"
            role="tab"
            aria-selected={mode === definition.id}
            className={`tab${mode === definition.id ? ' tab--active' : ''}`}
            onClick={() => onChange(definition.id)}
          >
            {definition.label}
          </button>
        ))}
      </div>
      {active ? <p className="tabs__description">{active.description}</p> : null}
    </div>
  )
}
