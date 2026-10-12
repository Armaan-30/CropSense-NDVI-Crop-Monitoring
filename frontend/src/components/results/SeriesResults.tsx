import { MessageList } from '@/components/common/Callout'
import { Panel } from '@/components/common/Panel'
import { TimeSeriesChart } from '@/components/charts/TimeSeriesChart'
import { TrendPanel } from '@/components/results/TrendPanel'
import {
  aggregationLabel,
  cloudMaskLabel,
  formatCount,
  formatDate,
  formatDuration,
  formatFraction,
  formatNDVI,
  formatTimestamp,
} from '@/utils/format'
import type { TimeSeriesResponse } from '@/types/api'

interface SeriesResultsProps {
  result: TimeSeriesResponse
}

/** Everything the `/api/ndvi/timeseries` response has to say. */
export function SeriesResults({ result }: SeriesResultsProps) {
  const plotted = result.points.filter((point) => point.mean_ndvi !== null).length

  return (
    <div className="results">
      <MessageList warnings={result.warnings} notes={result.notes} />

      <Panel
        title="Mean NDVI over time"
        subtitle={`${aggregationLabel(result.aggregation)} · ${formatCount(plotted)} observation(s) with data`}
      >
        <TimeSeriesChart points={result.points} trend={result.trend} />
      </Panel>

      <Panel title="Trend" subtitle="Ordinary least squares on the mean NDVI series">
        <TrendPanel trend={result.trend} excludedPointCount={result.excluded_point_count} />
      </Panel>

      <Panel title="Observations" subtitle="One row per time step, most recent last" flush>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col" className="table__num">
                  Mean
                </th>
                <th scope="col" className="table__num">
                  Median
                </th>
                <th scope="col" className="table__num">
                  Min
                </th>
                <th scope="col" className="table__num">
                  Max
                </th>
                <th scope="col" className="table__num">
                  Cloud-free
                </th>
                <th scope="col" className="table__num">
                  Scenes
                </th>
              </tr>
            </thead>
            <tbody>
              {result.points.map((point) => (
                <tr key={point.date} className={point.mean_ndvi === null ? 'is-muted' : ''}>
                  <th scope="row">{formatDate(point.date)}</th>
                  <td className="table__num">{formatNDVI(point.mean_ndvi)}</td>
                  <td className="table__num">{formatNDVI(point.median_ndvi)}</td>
                  <td className="table__num">{formatNDVI(point.min_ndvi, 2)}</td>
                  <td className="table__num">{formatNDVI(point.max_ndvi, 2)}</td>
                  <td className="table__num">{formatFraction(point.valid_pixel_fraction)}</td>
                  <td className="table__num">{formatCount(point.scene_count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Series settings" subtitle="What produced this series">
        <dl className="kv">
          <dt>Collection</dt>
          <dd className="table__mono">{result.collection_id}</dd>
          <dt>Requested window</dt>
          <dd>
            {formatDate(result.requested_range.start_date)} –{' '}
            {formatDate(result.requested_range.end_date)}
          </dd>
          <dt>Time step</dt>
          <dd>{aggregationLabel(result.aggregation)}</dd>
          <dt>Scene cloud filter</dt>
          <dd>≤ {result.cloud_threshold_percent}%</dd>
          <dt>Pixel mask</dt>
          <dd>{cloudMaskLabel(result.cloud_mask_method)}</dd>
          <dt>Analysis scale</dt>
          <dd>{result.scale_m} m</dd>
          <dt>Excluded time steps</dt>
          <dd>
            {formatCount(result.excluded_point_count)}
            <small> dropped for insufficient cloud-free coverage</small>
          </dd>
        </dl>
      </Panel>

      <p className="results__footer">
        Computed {formatTimestamp(result.computed_at)} in {formatDuration(result.duration_ms)}.
      </p>
    </div>
  )
}
