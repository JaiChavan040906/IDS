import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, pct, time } from '../../api'
import { Badge, ErrorBox, Meter, useApi } from '../../components/ui'
import { BarList, SERIES, useVisual } from '../../components/charts'

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
  const have = data?.usable_feedback ?? 0
  const locked = !data || data.busy || have < need
  const lockReason = data?.busy ? 'A retraining run is already in progress'
    : have < need ? `Locked: needs ${need - have} more verified analyst decision${need - have === 1 ? '' : 's'} (${have} of ${need})`
      : 'Ready: start a retraining run'
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
            <span className="big-num" style={{ fontSize: 30 }}>{data ? `${have} / ${need}` : '–'}</span>
            <span className="muted">verified, trainable feedback items<br /><span className="faint small">minimum {need} to unlock retraining</span></span>
          </div>
          {data && <Meter value={Math.min(1, have / Math.max(1, need))} color={have >= need ? '' : 'amber'} />}
          <ErrorBox error={startErr} />
          <div className="row">
            <span title={lockReason} style={{ display: 'inline-flex' }}>
              <button className="btn primary" disabled={locked} onClick={start} title={lockReason}>
                {data?.busy ? 'Retraining in progress…' : locked ? 'Start retraining (locked)' : 'Start retraining'}
              </button>
            </span>
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

      {data?.demo_tools && <DemoTools need={need} have={have} demoCount={data.demo_decisions} onChange={reload} />}

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
  const visual = useVisual()
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
            {visual && r.base && r.candidate && (
              <div className="viz-card stack" style={{ gap: 14 }}>
                {[['Benchmark macro-F1 (reliable)', 'benchmark_macro_f1_reliable'], ['Held-out feedback accuracy', 'feedback_holdout_accuracy'],
                  ['Benchmark detection rate', 'benchmark_detection_rate']].map(([l, k]) => (
                  <BarList key={k} title={l} max={1} format={(v) => pct(v, 2)}
                    items={[{ label: job.base_version, value: r.base[k] ?? 0, color: SERIES[0] },
                      { label: job.candidate_version, value: r.candidate[k] ?? 0, color: SERIES[1] }]} />
                ))}
              </div>
            )}
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

function DemoTools({ need, have, demoCount, onChange }) {
  const suggested = Math.max(1, (need ?? 20) - (have ?? 0) - 1)   // leave one decision to make live
  const [count, setCount] = useState(suggested)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [error, setError] = useState(null)
  const run = async (method, body) => {
    setBusy(true); setError(null); setMsg(null)
    try {
      const r = await api('/admin/demo/feedback', { method, body })
      setMsg(method === 'POST'
        ? `Added ${r.created} demo decision${r.created === 1 ? '' : 's'}${r.created < r.requested ? ` (only ${r.created} open alerts were available)` : ''}.`
        : `Removed ${r.removed} demo decision${r.removed === 1 ? '' : 's'}; their alerts are open again.`)
      onChange()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }
  return (
    <div className="card stack" style={{ borderStyle: 'dashed' }}>
      <div className="card-head" style={{ margin: 0 }}><h3>Retraining demo</h3><Badge kind="candidate">presentation helper</Badge></div>
      <p className="muted small" style={{ margin: 0 }}>
        Adds clearly marked <b>demo</b> decisions (analyst &quot;demo&quot;, tag &quot;demo&quot;) to open alerts, already verified, so you can show the
        retraining threshold without reviewing {need} alerts by hand. Each demo decision <b>accepts the model&apos;s own prediction</b> and never uses
        the hidden true label. Tip: add {suggested} (you have {have} of {need}), then make the last decision live and verify it to unlock retraining.
      </p>
      <div className="row">
        <label className="field" style={{ width: 160 }}>Demo decisions to add
          <input type="number" min="1" max="200" value={count} onChange={(e) => setCount(Number(e.target.value))} />
        </label>
        <button className="btn" disabled={busy || count < 1} onClick={() => run('POST', { count, verified: true })}>Add demo decisions</button>
        <button className="btn ghost" disabled={busy || !demoCount} onClick={() => run('DELETE')}>Remove demo decisions ({demoCount})</button>
      </div>
      <p className="faint small" style={{ margin: 0 }}>Verified decisions now: {have} of {need}. Turn this card off with <span className="mono">demo_tools: false</span> in configs/app.yaml.</p>
      {msg && <div className="success">{msg}</div>}
      <ErrorBox error={error} />
    </div>
  )
}
