import { MessageList } from '@/components/common/Callout'
import { Panel } from '@/components/common/Panel'
import { ComparisonChart } from '@/components/charts/ComparisonChart'
import { ChangeSummaryPanel } from '@/components/results/ChangeSummaryPanel'
import { HealthSummaryPanel } from '@/components/results/HealthSummaryPanel'
import { ImageryProvenancePanel } from '@/components/results/ImageryProvenancePanel'
import { StatisticsPanel } from '@/components/results/StatisticsPanel'
import { formatDate, formatDuration, formatTimestamp } from '@/utils/format'
import type { ChangeDetectionResponse } from '@/types/api'

interface CompareResultsProps {
  result: ChangeDetectionResponse
}

/** Everything the `/api/ndvi/change` response has to say. */
export function CompareResults({ result }: CompareResultsProps) {
  const baselineRange = result.baseline_imagery.requested_range
  const recentRange = result.recent_imagery.requested_range

  return (
    <div className="results">
      <MessageList warnings={result.warnings} notes={result.notes} />

      <Panel
        title="NDVI change"
        subtitle={`${formatDate(baselineRange.start_date)}–${formatDate(
          baselineRange.end_date,
        )} compared with ${formatDate(recentRange.start_date)}–${formatDate(recentRange.end_date)}`}
      >
        <ChangeSummaryPanel
          change={result.change}
          baseline={result.baseline_statistics}
          recent={result.recent_statistics}
        />
      </Panel>

      <Panel
        title="Class distribution shift"
        subtitle="Share of each period's own classified area"
      >
        <ComparisonChart baseline={result.baseline_health} recent={result.recent_health} />
      </Panel>

      <div className="split">
        <Panel title="Baseline period" subtitle={`${baselineRange.start_date} → ${baselineRange.end_date}`}>
          <div className="stack">
            <StatisticsPanel statistics={result.baseline_statistics} />
            <HealthSummaryPanel health={result.baseline_health} hideCalibrationNote />
          </div>
        </Panel>

        <Panel title="Recent period" subtitle={`${recentRange.start_date} → ${recentRange.end_date}`}>
          <div className="stack">
            <StatisticsPanel statistics={result.recent_statistics} />
            <HealthSummaryPanel health={result.recent_health} />
          </div>
        </Panel>
      </div>

      <div className="split">
        <Panel title="Baseline imagery">
          <ImageryProvenancePanel imagery={result.baseline_imagery} />
        </Panel>
        <Panel title="Recent imagery">
          <ImageryProvenancePanel imagery={result.recent_imagery} />
        </Panel>
      </div>

      <p className="results__footer">
        Computed {formatTimestamp(result.computed_at)} in {formatDuration(result.duration_ms)}.
      </p>
    </div>
  )
}
