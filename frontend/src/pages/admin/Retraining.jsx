import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, pct, time } from '../../api'
import { Badge, ErrorBox, useApi } from '../../components/ui'

const CHECK_LABELS = {
  macro_f1_drop: ['Benchmark macro-F1 drop', 'at most', true],
  fpr_increase: ['Benchmark false-positive-rate increase', 'at most', true],
  feedback_accuracy_gain: ['Accuracy gain on held-out feedback', 'at least', true],
}

export default function Retraining() {
  const { data, error, reload } = useApi(() => api('/admin/retrain'), [], 3000)
  const [startErr, setStartErr] = useState(null)
  const [open, setOpen] = useState(null)
  const start = async () => {
    setStartErr(null)
    try { const j = await api('/admin/retrain', { method: 'POST' }); setOpen(j.id); reload() } catch (e) { setStartErr(e) }
  }
  const acc = data?.config?.acceptance
  const need = data?.config?.min_verified_feedback
  return (
    <div className="stack">
      <ErrorBox error={error} />
      <div className="grid g2">
        <div className="card stack">
          <h3 style={{ margin: 0 }}>Start a retraining run</h3>
          <p className="muted small" style={{ margin: 0 }}>
            Fine-tunes the active model on <b>verified</b> analyst feedback plus a sample of the original training data,
            recalibrates it, and evaluates it. It is registered as a <b>candidate</b>. Nothing is deployed until you approve and deploy it.
          </p>
          <div className="row">
            <span className="big-num" style={{ fontSize: 30 }}>{data?.usable_feedback ?? '–'}</span>
            <span className="muted">verified, trainable feedback items<br /><span className="faint small">minimum {need}</span></span>
          </div>
          <ErrorBox error={startErr} />
          <div className="row">
            <button className="btn primary" disabled={!data || data.busy || data.usable_feedback < need} onClick={start}>
              {data?.busy ? 'Retraining in progress…' : 'Start retraining'}
            </button>
            <Link to="/admin/feedback" className="btn ghost">Verify feedback</Link>
          </div>
        </div>
        <div className="card">
          <h3>Acceptance criteria (fixed before training)</h3>
          <p className="faint small">Copied into each job when it starts. A candidate that fails any check cannot be approved.</p>
          {acc && (
            <table><tbody>
              <tr><td>Benchmark macro-F1 (reliable classes) may drop by</td><td className="mono right">≤ {pct(acc.max_macro_f1_drop)}</td></tr>
              <tr><td>Benchmark false-positive rate may rise by</td><td className="mono right">≤ {pct(acc.max_fpr_increase, 3)}</td></tr>
              <tr><td>Accuracy on held-out feedback must change by</td><td className="mono right">≥ {pct(acc.min_feedback_accuracy_gain)}</td></tr>
              <tr><td>Held-out share of feedback</td><td className="mono right">{pct(data.config.feedback_holdout_fraction, 0)}</td></tr>
            </tbody></table>
          )}
          <p className="faint small" style={{ marginTop: 10 }}>Benchmark = fixed validation half, never used for training.</p>
        </div>
      </div>

      <div className="card pad-0">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Job</th><th>Status</th><th>Base → candidate</th><th>Feedback</th><th>Result</th><th>Started</th><th /></tr></thead>
            <tbody>
              {data?.jobs.map((j) => (
                <tr key={j.id} className="click" onClick={() => setOpen(open === j.id ? null : j.id)}>
                  <td className="mono">#{j.id}</td>
                  <td><Badge kind={j.status}>{j.status === 'running' && <span className="pulse" />}{j.status}</Badge></td>
                  <td>{j.base_version} → {j.candidate_version || '…'}</td>
                  <td>{j.n_feedback}</td>
                  <td>{j.passed === null ? '–' : <Badge kind={j.passed ? 'passed' : 'failed'}>{j.passed ? 'passed' : 'failed'}</Badge>}</td>
                  <td className="small faint">{time(j.created_at)} by {j.created_by}</td>
                  <td className="small">{open === j.id ? '▲' : '▼'}</td>
                </tr>
              ))}
              {data && !data.jobs.length && <tr><td colSpan={7} className="muted">No retraining runs yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {open && data?.jobs.find((j) => j.id === open) && <JobDetail job={data.jobs.find((j) => j.id === open)} />}
    </div>
  )
}

function JobDetail({ job }) {
  const r = job.results || {}
  return (
    <div className="grid g2">
      <div className="card">
        <div className="card-head"><h3>Job #{job.id} evaluation</h3>
          {job.candidate_version && <Link to="/admin/models" className="small">Decide in Models →</Link>}</div>
        {r.checks ? (
          <>
            <table>
              <thead><tr><th>Check</th><th className="right">Value</th><th className="right">Limit</th><th /></tr></thead>
              <tbody>{Object.entries(r.checks).map(([k, c]) => (
                <tr key={k}><td>{CHECK_LABELS[k]?.[0] || k}</td>
                  <td className="mono right">{pct(c.value, 3)}</td>
                  <td className="mono right">{c.rule} {pct(c.limit, 3)}</td>
                  <td><Badge kind={c.passed ? 'passed' : 'failed'}>{c.passed ? 'pass' : 'fail'}</Badge></td></tr>
              ))}</tbody>
            </table>
            <h3 style={{ marginTop: 18 }}>Base vs candidate</h3>
            <table>
              <thead><tr><th>Metric</th><th className="right">{job.base_version}</th><th className="right">{job.candidate_version}</th></tr></thead>
              <tbody>{[
                ['Benchmark accuracy', 'benchmark_accuracy', 3], ['Benchmark macro-F1 (reliable)', 'benchmark_macro_f1_reliable', 2],
                ['Benchmark FPR', 'benchmark_fpr', 3], ['Benchmark detection rate', 'benchmark_detection_rate', 2],
                ['Benchmark referral rate', 'benchmark_referral_rate', 2], ['Held-out feedback accuracy', 'feedback_holdout_accuracy', 1],
                ['Training feedback accuracy', 'feedback_train_accuracy', 1],
              ].map(([l, k, d]) => (
                <tr key={k}><td>{l}</td><td className="mono right">{pct(r.base?.[k], d)}</td><td className="mono right">{pct(r.candidate?.[k], d)}</td></tr>
              ))}</tbody>
            </table>
            <p className="faint small" style={{ marginTop: 8 }}>{r.n_feedback_train} feedback items used for training, {r.n_feedback_holdout} held out.</p>
          </>
        ) : <p className="muted">Results appear when the job finishes.</p>}
      </div>
      <div className="card">
        <h3>Log</h3>
        <pre className="log">{job.log || 'Waiting…'}</pre>
      </div>
    </div>
  )
}
