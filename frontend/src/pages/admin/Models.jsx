import { useState } from 'react'
import { api, pct, time } from '../../api'
import { Badge, ErrorBox, useApi } from '../../components/ui'
import { BarList, SERIES, useVisual } from '../../components/charts'

export default function Models() {
  const { data, error, reload } = useApi(() => api('/admin/models'), [], 5000)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const act = async (path, label) => {
    const note = window.prompt(`${label}: optional note for the audit log`, '')
    if (note === null) return
    setErr(null); setMsg(null)
    try { await api(path, { method: 'POST', body: { note } }); setMsg(`${label} done.`); reload() } catch (e) { setErr(e) }
  }
  const active = data?.find((m) => m.status === 'active')
  const visual = useVisual()
  const bench = (m) => m.metrics?.benchmark || {}
  return (
    <div className="stack">
      <ErrorBox error={error || err} />
      {msg && <div className="success">{msg}</div>}
      <div className="row between">
        <span className="muted">Lifecycle: candidate → approved → active → retired. Only candidates that passed their criteria can be approved.</span>
        <button className="btn danger" disabled={!active?.parent} onClick={() => act('/admin/models/rollback', `Roll back ${active?.version} to ${active?.parent}`)}>
          Roll back active model
        </button>
      </div>
      <div className="card pad-0"><div className="table-wrap">
        <table>
          <thead><tr><th>Version</th><th>Status</th><th>Parent</th><th>Benchmark</th><th>Criteria</th><th>Notes</th><th>Created</th><th>Actions</th></tr></thead>
          <tbody>
            {data?.map((m) => {
              const b = m.metrics?.benchmark || {}
              const macro = b.benchmark_macro_f1_reliable ?? b.macro_f1_reliable
              const fpr = b.benchmark_fpr ?? b.binary?.fpr
              return (
                <tr key={m.id}>
                  <td><b className="mono">{m.version}</b></td>
                  <td><Badge kind={m.status} /></td>
                  <td className="mono">{m.parent || '–'}</td>
                  <td className="small nowrap">macro-F1 {pct(macro)}<br />FPR {pct(fpr, 3)}</td>
                  <td>{m.metrics?.passed === undefined ? <span className="faint small">initial</span> : <Badge kind={m.metrics.passed ? 'passed' : 'failed'}>{m.metrics.passed ? 'passed' : 'failed'}</Badge>}</td>
                  <td className="small muted" style={{ maxWidth: 280, whiteSpace: 'pre-wrap' }}>{m.notes}</td>
                  <td className="small faint nowrap">{time(m.created_at)}{m.decided_by && <div>by {m.decided_by}</div>}</td>
                  <td className="nowrap">
                    <div className="row" style={{ gap: 6 }}>
                      {m.status === 'candidate' && <button className="btn sm primary" disabled={!m.metrics?.passed} onClick={() => act(`/admin/models/${m.version}/approve`, `Approve ${m.version}`)}>Approve</button>}
                      {['candidate', 'approved'].includes(m.status) && <button className="btn sm danger" onClick={() => act(`/admin/models/${m.version}/reject`, `Reject ${m.version}`)}>Reject</button>}
                      {m.status === 'approved' && <button className="btn sm primary" onClick={() => act(`/admin/models/${m.version}/deploy`, `Deploy ${m.version}`)}>Deploy</button>}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div></div>
      {visual && data?.length > 0 && (
        <div className="card">
          <BarList title="Benchmark macro-F1 (reliable classes) per model version" color={SERIES[0]} max={1}
            items={data.map((m) => ({ label: `${m.version} (${m.status})`,
              value: bench(m).benchmark_macro_f1_reliable ?? bench(m).macro_f1_reliable ?? 0 }))}
            format={(v) => pct(v, 2)} />
        </div>
      )}
    </div>
  )
}
