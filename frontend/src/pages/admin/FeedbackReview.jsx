import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, time } from '../../api'
import { Badge, Empty, ErrorBox, useApi } from '../../components/ui'

export default function FeedbackReview() {
  const [filter, setFilter] = useState('false')
  const { data, error, reload } = useApi(() => api('/admin/feedback', { params: { verified: filter } }), [filter])
  const [busy, setBusy] = useState(null)
  const verify = async (id, verified) => {
    setBusy(id)
    try { await api(`/admin/feedback/${id}/verify`, { method: 'POST', body: { verified } }); reload() } finally { setBusy(null) }
  }
  return (
    <div className="stack">
      <div className="note">
        Only <b>verified</b> feedback is used for retraining. Check that the analyst's reason supports the label before verifying.
        "Unsure" decisions and new attack types stay in the Knowledge Repository but are never used to train.
      </div>
      <div className="seg" style={{ alignSelf: 'flex-start' }}>
        {[['false', 'Waiting'], ['true', 'Verified'], ['', 'All']].map(([v, l]) => (
          <button key={l} className={filter === v ? 'on' : ''} onClick={() => setFilter(v)}>{l}</button>
        ))}
      </div>
      <ErrorBox error={error} />
      {data && !data.length ? <Empty title="Nothing to verify">New analyst decisions will appear here.</Empty> : (
        <div className="card pad-0"><div className="table-wrap">
          <table>
            <thead><tr><th>Alert</th><th>Model said</th><th>Analyst label</th><th>Reason / evidence</th><th>Analyst</th><th /></tr></thead>
            <tbody>
              {data?.map((f) => (
                <tr key={f.id}>
                  <td><Link to={`/analyst/alerts/${f.alert_id}`}>#{f.alert_id}</Link><div className="faint small mono">{f.src_ip} → {f.dst_ip}:{f.dst_port}</div></td>
                  <td>{f.predicted_class}<div><Badge kind={f.decision}>{f.decision === 'review' ? 'review' : 'confident'}</Badge></div></td>
                  <td><Badge kind={f.verdict} /> <b>{f.verdict === 'benign' ? 'BENIGN' : f.attack_class}</b>
                    {f.attack_class !== f.predicted_class && f.verdict !== 'unsure' && <div className="small" style={{ color: 'var(--amber)' }}>corrects the model</div>}</td>
                  <td className="small" style={{ maxWidth: 360 }}>{f.reason}{f.evidence && <div className="faint">Evidence: {f.evidence}</div>}</td>
                  <td className="small">{f.analyst}<div className="faint">{f.confidence} conf. · {time(f.created_at)}</div></td>
                  <td className="nowrap">
                    {f.verified
                      ? <><Badge kind="verified">verified</Badge>{!f.used_in_version && <button className="btn sm ghost" disabled={busy === f.id} onClick={() => verify(f.id, false)}>Undo</button>}</>
                      : f.verdict === 'unsure' ? <span className="faint small">not trainable</span>
                        : <button className="btn sm primary" disabled={busy === f.id} onClick={() => verify(f.id, true)}>Verify</button>}
                    {f.used_in_version && <div className="faint small">in {f.used_in_version}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div></div>
      )}
    </div>
  )
}
