import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, pct, PROTO, time } from '../../api'
import { useAuth } from '../../auth'
import { Badge, ErrorBox, Meter, useApi } from '../../components/ui'

export default function AlertDetail() {
  const { id } = useParams()
  const { data: a, error, reload } = useApi(() => api(`/alerts/${id}`), [id])
  const meta = useApi(() => api('/meta'))
  const { user } = useAuth()
  const nav = useNavigate()
  const th = meta.data?.thresholds

  if (error) return <ErrorBox error={error} />
  if (!a) return <div className="page-loading">Loading alert…</div>

  const claim = async () => { await api(`/alerts/${id}/claim`, { method: 'POST' }); reload() }

  return (
    <div className="stack">
      <div className="row between">
        <div className="row">
          <button className="btn sm ghost" onClick={() => nav(-1)}>← Back</button>
          <h2 style={{ margin: 0 }}>Alert #{a.id}: {a.predicted_class}</h2>
          <Badge kind={a.severity} /><Badge kind={a.decision}>{a.decision === 'review' ? 'needs review' : 'confident alert'}</Badge><Badge kind={a.status} />
        </div>
        {a.status === 'open' && a.assigned_to !== user.username && (
          <button className="btn" onClick={claim}>{a.assigned_to ? `Take over from ${a.assigned_to}` : 'Assign to me'}</button>
        )}
      </div>

      <div className="grid g3">
        <div className="card">
          <h3>Flow context</h3>
          <dl className="kv">
            <dt>Source</dt><dd className="mono">{a.src_ip}:{a.src_port}</dd>
            <dt>Destination</dt><dd className="mono">{a.dst_ip}:{a.dst_port}</dd>
            <dt>Protocol</dt><dd>{PROTO[a.protocol] || a.protocol}</dd>
            <dt>Flow time</dt><dd>{time(a.flow_time)}</dd>
            <dt>Captured</dt><dd>{a.flow_day} · row {a.flow_row_id}</dd>
            <dt>Alert raised</dt><dd>{time(a.created_at)}</dd>
            <dt>Model</dt><dd>{a.model_version}</dd>
            <dt>Assigned</dt><dd>{a.assigned_to || '–'}</dd>
          </dl>
          <p className="faint small" style={{ marginTop: 12 }}>IPs, ports and time are context for you only; the model never sees them.</p>
        </div>

        <div className="card">
          <h3>Model verdict</h3>
          <div className="stack" style={{ gap: 12 }}>
            {a.top_classes.map((t) => (
              <div key={t.class}>
                <div className="row between small"><span>{t.class}</span><span className="mono">{pct(t.prob, 1)}</span></div>
                <Meter value={t.prob} color={t.class === 'BENIGN' ? '' : 'red'} />
              </div>
            ))}
            {a.second_opinion && (
              <div className="row between small">
                <span>Second opinion (Random Forest)</span>
                <span>
                  <b>{a.second_opinion.class}</b> <span className="mono faint">{pct(a.second_opinion.confidence, 0)}</span>
                  {a.second_opinion.class !== a.predicted_class && <Badge kind="medium">disagrees</Badge>}
                </span>
              </div>
            )}
            <hr style={{ border: 0, borderTop: '1px solid var(--border)', margin: '4px 0' }} />
            <div>
              <div className="row between small"><span>Uncertainty (entropy)</span><span className="mono">{a.entropy.toFixed(3)}</span></div>
              <Meter value={a.entropy} max={Math.max(th?.entropy * 3 || 0.3, a.entropy)} threshold={th?.entropy} color="amber" />
            </div>
            <div>
              <div className="row between small"><span>Unlike known traffic (distance)</span><span className="mono">{a.distance.toFixed(0)}</span></div>
              <Meter value={Math.log1p(a.distance)} max={Math.max(Math.log1p(th?.distance || 1) * 1.6, Math.log1p(a.distance))} threshold={th ? Math.log1p(th.distance) : undefined} color="amber" />
            </div>
            <div className="small">
              {a.reasons?.length ? a.reasons.map((r) => <div key={r}>• {r}</div>) : <span className="muted">Confident prediction; below both review thresholds (white marks).</span>}
            </div>
          </div>
        </div>

        <div className="card">
          <h3>What stands out</h3>
          <p className="faint small">Features furthest from typical training traffic (z-score after scaling).</p>
          <table>
            <tbody>
              {a.evidence.map((e) => (
                <tr key={e.feature}>
                  <td className="small">{e.feature}</td>
                  <td className="mono small right">{e.value === null ? '–' : Number(e.value).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                  <td className="right"><Badge kind={Math.abs(e.z) > 3 ? 'medium' : ''}>{e.z > 0 ? '▲' : '▼'} {Math.abs(e.z)}σ</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid g2">
        <FeedbackPanel alert={a} classes={meta.data?.classes || []} onSaved={reload} />
        <div className="card">
          <div className="card-head"><h3>Similar past incidents</h3><Link to="/analyst/kr" className="small">Search KR →</Link></div>
          {a.similar_incidents.length ? (
            <div className="stack" style={{ gap: 10 }}>
              {a.similar_incidents.map((s) => (
                <Link key={s.id} to={`/analyst/kr/${s.id}`} className="card" style={{ padding: 14, color: 'inherit', textDecoration: 'none' }}>
                  <div className="row between">
                    <b>{s.attack_class}</b>
                    <span className="row" style={{ gap: 6 }}><Badge kind={s.verdict} />{s.verified && <Badge kind="verified">verified</Badge>}<span className="mono small faint">{pct(s.similarity, 0)} similar</span></span>
                  </div>
                  <div className="small muted" style={{ marginTop: 4 }}>{s.title}</div>
                  <div className="small" style={{ marginTop: 6, whiteSpace: 'pre-wrap' }}>{s.text.slice(0, 220)}{s.text.length > 220 ? '…' : ''}</div>
                  <div className="faint small" style={{ marginTop: 6 }}>{s.analyst} · {time(s.created_at)}</div>
                </Link>
              ))}
            </div>
          ) : <p className="muted">No incidents in the Knowledge Repository yet. Your decision will be the first.</p>}
        </div>
      </div>
    </div>
  )
}

function FeedbackPanel({ alert, classes, onSaved }) {
  const nav = useNavigate()
  const attackClasses = classes.filter((c) => c !== 'BENIGN')
  const [f, setF] = useState({
    verdict: '', attack_class: alert.predicted_class !== 'BENIGN' ? alert.predicted_class : '',
    reason: '', context: '', evidence: '', confidence: 'medium', comments: '', tags: '',
  })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target ? e.target.value : e })

  if (alert.feedback.length) {
    return (
      <div className="card">
        <h3>Decision recorded</h3>
        {alert.feedback.map((fb) => (
          <div key={fb.id} className="stack" style={{ gap: 8 }}>
            <div className="row"><Badge kind={fb.verdict} />{fb.verdict !== 'benign' && <b>{fb.attack_class}</b>}<Badge>{fb.confidence} confidence</Badge>{fb.verified ? <Badge kind="verified">verified by {fb.verified_by}</Badge> : <Badge kind="candidate">awaiting admin verification</Badge>}</div>
            <dl className="kv">
              <dt>Reason</dt><dd>{fb.reason}</dd>
              {fb.context && <><dt>Context</dt><dd>{fb.context}</dd></>}
              {fb.evidence && <><dt>Evidence</dt><dd>{fb.evidence}</dd></>}
              {fb.comments && <><dt>Comments</dt><dd>{fb.comments}</dd></>}
              <dt>By</dt><dd>{fb.analyst} · {time(fb.created_at)}</dd>
              {fb.used_in_version && <><dt>Used in</dt><dd>model {fb.used_in_version}</dd></>}
            </dl>
          </div>
        ))}
      </div>
    )
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api(`/alerts/${alert.id}/feedback`, {
        method: 'POST',
        body: { ...f, attack_class: f.verdict === 'benign' ? 'BENIGN' : f.verdict === 'unsure' ? (f.attack_class || 'UNKNOWN_ATTACK') : f.attack_class, tags: f.tags.split(',').map((t) => t.trim()).filter(Boolean) },
      })
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card stack" onSubmit={submit}>
      <div className="card-head" style={{ margin: 0 }}><h3>Your decision</h3>
        <button type="button" className="btn sm ghost" onClick={() => nav('/analyst/review')}>Skip</button></div>
      <div>
        <div className="faint small" style={{ marginBottom: 6 }}>Verdict</div>
        <div className="seg">
          {[['malicious', 'Malicious'], ['benign', 'Benign (false positive)'], ['unsure', 'Unsure']].map(([v, l]) => (
            <button type="button" key={v} className={`${f.verdict === v ? 'on' : ''} ${v}`} onClick={() => set('verdict')(v)}>{l}</button>
          ))}
        </div>
      </div>
      {f.verdict === 'malicious' && (
        <label className="field">Attack type
          <select value={f.attack_class} onChange={set('attack_class')} required>
            <option value="">Choose…</option>
            {attackClasses.map((c) => <option key={c}>{c}</option>)}
            <option value="UNKNOWN_ATTACK">Other / new attack type (not used for retraining)</option>
          </select>
        </label>
      )}
      <label className="field">Reason <span className="hint">Why did you decide this? (required)</span>
        <textarea value={f.reason} onChange={set('reason')} required minLength={3} placeholder="e.g. Repeated SYN to many ports from one host within seconds" />
      </label>
      <div className="grid g2">
        <label className="field">Context <span className="hint">What else was happening?</span>
          <textarea value={f.context} onChange={set('context')} placeholder="e.g. Host is a known vulnerability scanner run by IT" />
        </label>
        <label className="field">Evidence <span className="hint">What did you check?</span>
          <textarea value={f.evidence} onChange={set('evidence')} placeholder="e.g. Firewall log, asset inventory, packet capture" />
        </label>
      </div>
      <div className="grid g2">
        <div>
          <div className="faint small" style={{ marginBottom: 6 }}>Your confidence</div>
          <div className="seg">
            {['low', 'medium', 'high'].map((c) => <button type="button" key={c} className={f.confidence === c ? 'on' : ''} onClick={() => set('confidence')(c)}>{c}</button>)}
          </div>
        </div>
        <label className="field">Tags <span className="hint">comma separated</span>
          <input value={f.tags} onChange={set('tags')} placeholder="scanner, internal, false-positive" />
        </label>
      </div>
      <label className="field">Comments
        <textarea value={f.comments} onChange={set('comments')} style={{ minHeight: 50 }} />
      </label>
      {error && <div className="error">{error}</div>}
      <button className="btn primary" disabled={busy || !f.verdict || (f.verdict === 'malicious' && !f.attack_class)}>
        {busy ? 'Saving…' : 'Save decision to Knowledge Repository'}
      </button>
    </form>
  )
}
