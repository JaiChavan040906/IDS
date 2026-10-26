import { useState } from 'react'
import { api } from '../../api'
import { BarList, SERIES } from '../../components/charts'
import { ErrorBox, useApi } from '../../components/ui'

export function SampleTable({ name, limit = 8, title }) {
  const { data, error } = useApi(() => api(`/dw/tables/${name}`, { params: { limit } }), [name, limit])
  return (
    <div className="card pad-0">
      <div className="card-head" style={{ padding: '16px 16px 0' }}>
        <h3>{title || <>First rows of <code>{name}</code></>}</h3>
      </div>
      <ErrorBox error={error} />
      <div className="table-wrap">
        <table>
          <thead><tr>{data?.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>
            {data?.rows.map((r, i) => (
              <tr key={i}>{r.map((v, j) => <td key={j} className="mono small">{v === null ? <span className="faint">NULL</span> : String(v)}</td>)}</tr>
            ))}
            {data && !data.rows.length && <tr><td className="muted">No rows yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function Comparison({ which }) {
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true)
    try { setRes(await api(`/dw/compare/${which}`)); setErr(null) } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  return (
    <div className="card">
      <div className="card-head">
        <h3>{res?.title || (which === 'snowflake' ? 'Star schema vs snowflake schema' : 'Base fact table vs aggregate fact table')}</h3>
        <button className="btn sm primary" onClick={run} disabled={busy}>{busy ? 'Running…' : res ? 'Run again' : 'Run both queries'}</button>
      </div>
      <ErrorBox error={err} />
      {!res && <p className="muted" style={{ margin: 0 }}>Runs the same question two ways on the real warehouse and times each (best of 3).</p>}
      {res && (
        <>
          <p style={{ marginTop: 0 }}>Question: <b>{res.question}</b>{' '}
            {res.same_answer ? <span className="badge benign">same answer</span> : <span className="badge malicious">answers differ</span>}</p>
          <div style={{ marginBottom: 16 }}>
            <BarList title="Query time (ms, best of 3) — shorter is faster"
              items={res.runs.map((r, i) => ({ label: r.label.split(':')[0].split(' (')[0], value: r.ms, color: SERIES[i] }))}
              format={(v) => `${v} ms`} />
          </div>
          <div className="grid g2">
            {res.runs.map((r) => (
              <div key={r.label}>
                <div className="row between" style={{ marginBottom: 6 }}>
                  <b>{r.label}</b>
                  <span className="mono" style={{ color: 'var(--accent)' }}>{r.ms} ms</span>
                </div>
                <div className="faint small" style={{ marginBottom: 6 }}>
                  scans {r.rows_scanned.toLocaleString()} rows → {r.result_rows} result rows
                </div>
                <pre className="log">{r.sql}</pre>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
