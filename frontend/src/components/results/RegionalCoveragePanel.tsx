import { useState } from 'react'
import { Callout } from '@/components/common/Callout'
import { Panel } from '@/components/common/Panel'
import { formatArea, formatNDVI, formatPercent, formatTimestamp } from '@/utils/format'
import { parseRegionalCoverageReport } from '@/services/regionalReport'
import type { RegionalCoverageReport } from '@/types/regional'

function basisLabel(basis: RegionalCoverageReport['denominator']['basis']): string {
  if (basis === 'net_sown') return 'net sown area'
  if (basis === 'gross_cropped') return 'gross cropped area'
  return basis === 'other' ? 'other area basis' : 'unspecified area basis'
}

/** Displays an operator-generated pilot report without sending the file to the server. */
export function RegionalCoveragePanel() {
  const [report, setReport] = useState<RegionalCoverageReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadReport = async (file: File | undefined) => {
    if (!file) return
    try {
      const parsed = parseRegionalCoverageReport(JSON.parse(await file.text()) as unknown)
      if (!parsed) throw new Error('This JSON does not match a CropSense regional coverage report.')
      setReport(parsed)
      setError(null)
    } catch (cause) {
      setReport(null)
      setError(cause instanceof Error ? cause.message : 'Could not read this report file.')
    }
  }

  return (
    <Panel title="Regional pilot coverage" subtitle="Load a report from the authorized pilot runner">
      <div className="stack">
        <label className="field">
          <span className="field__label">Coverage report (JSON)</span>
          <input
            className="file-input"
            type="file"
            accept="application/json,.json"
            aria-label="Coverage report JSON"
            onChange={(event) => void loadReport(event.currentTarget.files?.[0])}
          />
          <span className="field__hint">
            The report stays in this browser. It is produced by scripts/run_regional_monitor.py.
          </span>
        </label>

        {error ? <Callout variant="warning" title="Report not loaded">{error}</Callout> : null}
        {!report && !error ? (
          <p className="hint">
            No regional report loaded. You can still run single-area Sentinel-2 analyses now by
            drawing a field or using the Maharashtra demo rectangle. Multi-farm hectare coverage
            reports require authorized field boundaries and a matching official denominator.
          </p>
        ) : null}

        {report ? (
          <div className="stack">
            <dl className="kv">
              <dt>Region / season</dt>
              <dd>{report.region} · {report.season}</dd>
              <dt>Run status</dt>
              <dd>{report.state} · updated {formatTimestamp(report.updated_at)}</dd>
              <dt>Analysis window</dt>
              <dd>{report.date_window.start} – {report.date_window.end}</dd>
              <dt>Coverage target</dt>
              <dd>{formatPercent(report.target.fraction * 100)} of {formatArea(report.denominator.cultivated_area_ha)} {basisLabel(report.denominator.basis)}</dd>
              <dt>Denominator source</dt>
              <dd>{report.denominator.source} · as of {report.denominator.as_of}</dd>
            </dl>

            <div className="coverage-metric">
              <div className="coverage-metric__heading">
                <strong>Processed</strong>
                <span>{formatArea(report.target.processed_area_ha)} · {formatPercent(report.target.processed_percent)}</span>
              </div>
              <progress max={100} value={Math.min(100, report.target.processed_percent)} aria-label="Processed cultivated area" />
            </div>
            <div className="coverage-metric">
              <div className="coverage-metric__heading">
                <strong>Cloud-valid observations</strong>
                <span>{formatArea(report.target.cloud_valid_area_ha)} · {formatPercent(report.target.cloud_valid_percent)}</span>
              </div>
              <progress max={100} value={Math.min(100, report.target.cloud_valid_percent)} aria-label="Cloud-valid cultivated area" />
            </div>

            <p className="hint">
              {report.target.target_met
                ? 'The cloud-valid area met the configured coverage target for this denominator.'
                : 'The cloud-valid area has not met the configured target. Processed area alone does not count cloudy fields as observed.'}
            </p>

            {report.accuracy === null ? (
              <Callout variant="caution" title="Accuracy not measured">{report.accuracy_note}</Callout>
            ) : null}

            <table className="table">
              <thead>
                <tr><th scope="col">Field ID</th><th scope="col">Status</th><th scope="col" className="table__num">Mean NDVI</th><th scope="col" className="table__num">Valid area</th></tr>
              </thead>
              <tbody>
                {report.fields.map((field) => (
                  <tr key={field.field_id}>
                    <th scope="row" className="table__mono">{field.field_id}</th>
                    <td>{field.state}</td>
                    <td className="table__num">{formatNDVI(field.mean_ndvi)}</td>
                    <td className="table__num">{field.usable_area_ha === null ? '—' : formatArea(field.usable_area_ha)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="hint">Read each field’s warnings and error details in the downloaded JSON report. A missing observation is not a low NDVI.</p>
          </div>
        ) : null}
      </div>
    </Panel>
  )
}
