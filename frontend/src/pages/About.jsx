import { Link } from 'react-router-dom'
import { api, pct } from '../api'
import { useApi } from '../components/ui'
import { SERIES, SplitBar, useVisual } from '../components/charts'
import { useAuth } from '../auth'

const STEPS = [
  ['01', 'Detect', 'A hybrid CNN-LSTM scores every network flow (64 CICFlowMeter features) into benign or one of 12 attack classes.'],
  ['02', 'Know what it does not know', 'Calibrated confidence, a distance-to-known-traffic check, and a Random Forest second opinion flag flows that are uncertain, including attacks the model has never seen.'],
  ['03', 'Ask a human', 'Only uncertain flows go to the security analyst, with context, evidence and similar past incidents from the Knowledge Repository.'],
  ['04', 'Learn safely', 'Verified analyst decisions train a candidate model. It must pass acceptance criteria fixed in advance, and an administrator approves every deployment.'],
]

const FLOW = [
  ['Traffic', 'replayed test flows'],
  ['CNN-LSTM', 'classify'],
  ['Uncertainty', 'entropy · distance · 2nd opinion'],
  ['Analyst', 'review + context'],
  ['Knowledge Repo', 'incidents'],
  ['Retraining', 'admin-approved'],
]

export default function About() {
  const { user } = useAuth()
  const { data } = useApi(() => api('/public/summary'))
  const m = data?.metrics
  const visual = useVisual()
  const r = data?.routing?.referral_rate
  return (
    <>
      <section className="hero">
        <div className="container">
          <span className="eyebrow"><span className="dot" /> Human-in-the-loop intrusion detection</span>
          <h1>An IDS that knows <em>when to ask</em> for help.</h1>
          <p className="lead">
            Sentinel flags suspicious network flows, sends the uncertain ones to a security analyst,
            remembers every decision, and improves only through controlled, approved retraining.
          </p>
          <div className="row" style={{ justifyContent: 'center' }}>
            {user ? (
              <Link className="btn primary lg" to={user.role === 'admin' ? '/admin' : '/analyst'}>Open your console →</Link>
            ) : (
              <Link className="btn primary lg" to="/login">Sign in to the console →</Link>
            )}
            <a className="btn lg" href="#how">How it works</a>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="grid g4">
            <div className="card"><span className="kicker">Accuracy</span><div className="big-num">{m ? pct(m.accuracy) : '–'}</div><p className="muted small">13 classes, validation set</p></div>
            <div className="card"><span className="kicker">Macro-F1</span><div className="big-num">{m ? pct(m.macro_f1_reliable) : '–'}</div><p className="muted small">excl. classes with &lt;100 samples</p></div>
            <div className="card"><span className="kicker">False alarms</span><div className="big-num">{m ? pct(m.binary?.fpr, 3) : '–'}</div><p className="muted small">of benign flows flagged</p></div>
            <div className="card"><span className="kicker">Sent to analyst</span><div className="big-num">{data?.routing ? pct(data.routing.referral_rate, 1) : '–'}</div><p className="muted small">the rest is handled automatically</p></div>
          </div>
          {visual && r !== undefined && (
            <div className="card" style={{ marginTop: 16 }}>
              <SplitBar title="How traffic is handled (validation set)" format={(v) => `${(100 * v).toFixed(2)}%`}
                parts={[{ label: 'Handled automatically', value: 1 - r, color: SERIES[0] },
                  { label: 'Sent to the analyst', value: r, color: SERIES[1] }]} />
            </div>
          )}
          <p className="faint small" style={{ marginTop: 12, textAlign: 'center' }}>
            Active model {data?.model_version || '–'} · Improved CIC-IDS2017 (Engelen et al.) · numbers from the held-out validation set
          </p>
        </div>
      </section>

      <section className="section" id="how">
        <div className="container">
          <div className="section-title">
            <span className="kicker">How it works</span>
            <h2>Automate the confident. Escalate the uncertain.</h2>
            <p>Most traffic is routine. The model handles it, and your analysts spend their time where the model is genuinely unsure.</p>
          </div>
          <div className="flow-diagram" style={{ marginBottom: 40 }}>
            {FLOW.map(([t, s], i) => (
              <div key={t} style={{ display: 'contents' }}>
                <div className="node"><b>{t}</b><span>{s}</span></div>
                {i < FLOW.length - 1 && <div className="arrow">→</div>}
              </div>
            ))}
          </div>
          <div className="grid g4">
            {STEPS.map(([n, t, d]) => (
              <div className="card step" key={n}><span className="n">{n}</span><h3>{t}</h3><p>{d}</p></div>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="section-title">
            <span className="kicker">Two roles</span>
            <h2>Built for the people who run it</h2>
          </div>
          <div className="grid g2">
            <div className="card glow">
              <h3>Security Analyst</h3>
              <p className="muted">Works the review queue: sees the flow's context, the model's confidence and why it hesitated, the most unusual features, and similar past incidents. Records a decision with reason, context, evidence and confidence.</p>
              <Link to="/analyst">Go to analyst console →</Link>
            </div>
            <div className="card">
              <h3>Administrator</h3>
              <p className="muted">Manages users and roles, verifies analyst feedback, launches retraining, compares candidate models against fixed acceptance criteria, and approves, deploys or rolls back model versions. Every action is audited.</p>
              <Link to="/admin">Go to administration →</Link>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="grid g3">
            <div className="card">
              <span className="kicker">Model</span>
              <p className="muted">Conv1D(64) → MaxPool → Conv1D(128) → LSTM(128) → Dropout → softmax, following Table 5 of the reference paper (MDPI, 2025). Temperature scaling for calibration, plus a Random Forest second opinion for routing.</p>
            </div>
            <div className="card">
              <span className="kicker">Data</span>
              <p className="muted">Improved CIC-IDS2017: 1.71M de-duplicated flows over 5 days. Identifiers and destination port removed so the model cannot take shortcuts. Split 70/15/15 before any fitting.</p>
            </div>
            <div className="card">
              <span className="kicker">Safety</span>
              <p className="muted">The true label of replayed traffic is never used for prediction or shown to analysts; it is only used to evaluate the system. No model is deployed without passing its criteria and an admin's approval.</p>
            </div>
          </div>
        </div>
      </section>

      <footer className="footer">
        <div className="container row between">
          <span>Sentinel HITL IDS · TE Computer Engineering project</span>
          <span>Adaptive AI-based intrusion detection with human feedback</span>
        </div>
      </footer>
    </>
  )
}
