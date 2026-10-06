import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ago, api, pct, PROTO } from '../../api'
import { Badge, Empty, ErrorBox, useApi } from '../../components/ui'

const PAGE = 50

export default function AlertList({ decision, status, intro }) {
  const nav = useNavigate()
  const [severity, setSeverity] = useState('')
  const [cls, setCls] = useState('')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const meta = useApi(() => api('/meta'))
  const { data, error } = useApi(
    () => api('/alerts', { params: { decision, status, severity, predicted_class: cls, q, limit: PAGE, offset } }),
    [decision, status, severity, cls, q, offset], 5000)

  return (
    <div className="stack">
      {intro && <p className="muted" style={{ margin: 0 }}>{intro}</p>}
      <div className="filters">
        <input placeholder="Search IP…" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0) }} />
        <select value={severity} onChange={(e) => { setSeverity(e.target.value); setOffset(0) }}>
          <option value="">All severities</option><option>high</option><option>medium</option><option>low</option>
        </select>
        <select value={cls} onChange={(e) => { setCls(e.target.value); setOffset(0) }}>
          <option value="">All predicted classes</option>
          {meta.data?.classes.map((c) => <option key={c}>{c}</option>)}
        </select>
      </div>
      <ErrorBox error={error} />
      {data && !data.items.length ? <Empty title="Nothing here">No alerts match. New ones appear as traffic is replayed.</Empty> : (
        <div className="card pad-0">
          <div className="table-wrap">
            <table>
              <thead><tr>
                <th>#</th><th>Severity</th><th>Model says</th><th>Confidence</th><th>Source → Destination</th>
                <th>Proto</th><th>Why flagged</th><th>Status</th><th>Seen</th>
              </tr></thead>
              <tbody>
                {data?.items.map((a) => (
                  <tr key={a.id} className="click" onClick={() => nav(`/analyst/alerts/${a.id}`)}>
                    <td className="faint mono">{a.id}</td>
                    <td><Badge kind={a.severity} /></td>
                    <td><b>{a.predicted_class}</b><div><Badge kind={a.decision}>{a.decision === 'review' ? 'needs review' : 'confident'}</Badge></div></td>
                    <td className="mono">{pct(a.confidence, 1)}</td>
                    <td className="mono small nowrap">{a.src_ip}:{a.src_port}<br />→ {a.dst_ip}:{a.dst_port}</td>
                    <td>{PROTO[a.protocol] || a.protocol}</td>
                    <td className="small muted" style={{ maxWidth: 260 }}>{a.reasons?.length ? a.reasons.join('; ') : 'high-confidence attack'}</td>
                    <td><Badge kind={a.status} />{a.assigned_to && <div className="faint small">{a.assigned_to}</div>}</td>
                    <td className="faint small nowrap">{ago(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && (
            <div className="pager">
              <span className="faint small">{offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}</span>
              <button className="btn sm" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
              <button className="btn sm" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
