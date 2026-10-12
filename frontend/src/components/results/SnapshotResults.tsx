import { MessageList } from '@/components/common/Callout'
import { Panel } from '@/components/common/Panel'
import { HealthClassChart } from '@/components/results/HealthClassChart'
import { HealthSummaryPanel } from '@/components/results/HealthSummaryPanel'
import { ImageryProvenancePanel } from '@/components/results/ImageryProvenancePanel'
import { StatisticsPanel } from '@/components/results/StatisticsPanel'
import { formatDuration, formatTimestamp } from '@/utils/format'
import type { NDVIAnalyzeResponse } from '@/types/api'

interface SnapshotResultsProps {
  result: NDVIAnalyzeResponse
}

/** Everything the `/api/ndvi/analyze` response has to say, in reading order. */
export function SnapshotResults({ result }: SnapshotResultsProps) {
  return (
    <div className="results">
      <MessageList warnings={result.warnings} notes={result.notes} />

      <Panel
        title="NDVI statistics"
        subtitle="Zonal reduction over the analysed area, cloud-free pixels only"
      >
        <StatisticsPanel statistics={result.statistics} />
      </Panel>

      <Panel
        title="Vegetation health classes"
        subtitle="Area and share of the classified area in each NDVI band"
      >
        <div className="stack">
          <HealthClassChart classes={result.health.classes} />
          <HealthSummaryPanel health={result.health} />
        </div>
      </Panel>

      <Panel title="Imagery" subtitle="The scenes these numbers were computed from">
        <ImageryProvenancePanel imagery={result.imagery} />
      </Panel>

      <p className="results__footer">
        Computed {formatTimestamp(result.computed_at)} in {formatDuration(result.duration_ms)}.
      </p>
    </div>
  )
}
