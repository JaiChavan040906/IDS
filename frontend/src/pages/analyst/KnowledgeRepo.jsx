import { useState } from 'react'
import { Link, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { api, pct, PROTO, time } from '../../api'
import { Badge, Empty, ErrorBox, useApi } from '../../components/ui'

export default function KnowledgeRepo() {
  return (
    <Routes>
      <Route index element={<KRSearch />} />
      <Route path=":id" element={<KREntryView />} />
    </Routes>
  )
}

function KRSearch() {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [cls, setCls] = useState('')
  const [verdict, setVerdict] = useState('')
  const [verified, setVerified] = useState('')
  const meta = useApi(() => api('/meta'))
  const { data, error } = useApi(() => api('/kr', { params: { q, attack_class: cls, verdict, verified } }), [q, cls, verdict, verified])
  return (
    <div className="stack">
      <p className="muted" style={{ margin: 0 }}>Every analyst decision becomes an incident here. Search by text, or open an alert to see the incidents most similar to it.</p>
      <div className="filters">
        <input placeholder="Search reasons, context, evidence…" value={q} onChange={(e) => setQ(e.target.value)} style={{ minWidth: 280 }} />
        <select value={cls} onChange={(e) => setCls(e.target.value)}>
          <option value="">All labels</option>
          {meta.data?.classes.map((c) => <option key={c}>{c}</option>)}
          <option>UNKNOWN_ATTACK</option>
        </select>
        <select value={verdict} onChange={(e) => setVerdict(e.target.value)}>
          <option value="">All verdicts</option><option>malicious</option><option>benign</option><option>unsure</option>
        </select>
        <select value={verified} onChange={(e) => setVerified(e.target.value)}>
          <option value="">Verified or not</option><option value="true">Verified only</option><option value="false">Unverified only</option>
        </select>
      </div>
      <ErrorBox error={error} />
      {data && !data.length ? <Empty title="No incidents found">Decisions recorded on alerts appear here.</Empty> : (
        <div className="card pad-0"><div className="table-wrap">
          <table>
            <thead><tr><th>#</th><th>Label</th><th>Verdict</th><th>Title</th><th>Analyst</th><th>Recorded</th></tr></thead>
            <tbody>
              {data?.map((e) => (
                <tr key={e.id} className="click" onClick={() => nav(`/analyst/kr/${e.id}`)}>
                  <td className="faint mono">{e.id}</td>
                  <td><b>{e.attack_class}</b></td>
                  <td><Badge kind={e.verdict} /> {e.verified && <Badge kind="verified">verified</Badge>}</td>
                  <td className="small">{e.title}<div className="faint">{e.text.slice(0, 120)}</div></td>
                  <td className="small">{e.analyst}</td>
                  <td className="small faint nowrap">{time(e.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div></div>
      )}
    </div>
  )
}

function KREntryView() {
  const { id } = useParams()
  const { data: e, error } = useApi(() => api(`/kr/${id}`), [id])
  if (error) return <ErrorBox error={error} />
  if (!e) return <div className="page-loading">Loading…</div>
  const a = e.alert
  return (
    <div className="stack">
      <div className="row">
        <Link to="/analyst/kr" className="btn sm ghost">← Knowledge Repository</Link>
        <h2 style={{ margin: 0 }}>Incident #{e.id}: {e.attack_class}</h2>
        <Badge kind={e.verdict} />{e.verified && <Badge kind="verified">verified</Badge>}
      </div>
      <div className="grid g2">
        <div className="card">
          <h3>Analyst decision</h3>
          <dl className="kv">
            <dt>Reason</dt><dd>{e.feedback.reason}</dd>
            <dt>Context</dt><dd>{e.feedback.context || '–'}</dd>
            <dt>Evidence</dt><dd>{e.feedback.evidence || '–'}</dd>
            <dt>Confidence</dt><dd>{e.feedback.confidence}</dd>
            <dt>Comments</dt><dd>{e.feedback.comments || '–'}</dd>
            <dt>Tags</dt><dd>{e.tags.length ? e.tags.map((t) => <Badge key={t}>{t}</Badge>) : '–'}</dd>
            <dt>Analyst</dt><dd>{e.analyst} · {time(e.created_at)}</dd>
          </dl>
        </div>
        <div className="card">
          <div className="card-head"><h3>Original alert</h3><Link to={`/analyst/alerts/${a.id}`} className="small">Open alert #{a.id} →</Link></div>
          <dl className="kv">
            <dt>Flow</dt><dd className="mono">{a.src_ip}:{a.src_port} → {a.dst_ip}:{a.dst_port} ({PROTO[a.protocol] || a.protocol})</dd>
            <dt>Model said</dt><dd>{a.predicted_class} ({pct(a.confidence, 1)}), {a.decision === 'review' ? 'sent to review' : 'confident alert'}</dd>
            <dt>Why</dt><dd>{a.reasons.join('; ') || '–'}</dd>
            <dt>Model version</dt><dd>{a.model_version}</dd>
            <dt>Flow time</dt><dd>{time(a.flow_time)}</dd>
          </dl>
        </div>
      </div>
      <div className="card">
        <h3>Similar incidents</h3>
        {e.similar_incidents.length ? (
          <table>
            <thead><tr><th>Similarity</th><th>Label</th><th>Verdict</th><th>Reason</th></tr></thead>
            <tbody>{e.similar_incidents.map((s) => (
              <tr key={s.id}><td className="mono">{pct(s.similarity, 0)}</td><td><Link to={`/analyst/kr/${s.id}`}>{s.attack_class}</Link></td><td><Badge kind={s.verdict} /></td><td className="small">{s.text.slice(0, 160)}</td></tr>
            ))}</tbody>
          </table>
        ) : <p className="muted">No other incidents yet.</p>}
      </div>
    </div>
  )
}
