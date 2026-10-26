import { useState } from 'react'
import { api, num } from '../../api'
import { ErrorBox } from '../../components/ui'

const PHASE = {
  extract: { label: 'Extract', color: 'var(--blue)' },
  transform: { label: 'Transform', color: 'var(--amber)' },
  load: { label: 'Load', color: 'var(--accent)' },
}

export function EtlButtons({ state, onStart, built }) {
  const [err, setErr] = useState(null)
  const start = async (mode) => {
    try { await api('/dw/etl', { method: 'POST', body: { mode } }); setErr(null); onStart?.() } catch (e) { setErr(e) }
  }
  return (
    <div className="stack" style={{ gap: 8, alignItems: 'center' }}>
      <div className="row" style={{ justifyContent: 'center' }}>
        <button className="btn primary" disabled={state?.running} onClick={() => start('full')}
          title="Rebuild everything from the sources (about 30 seconds)">
          {state?.running && state.mode === 'full' ? 'Full load running…' : 'Run full load'}
        </button>
        {built && (
          <button className="btn" disabled={state?.running} onClick={() => start('incremental')}
            title="Only portal alerts added since the last load">
            {state?.running && state.mode === 'incremental' ? 'Incremental load running…' : 'Run incremental load'}
          </button>
        )}
      </div>
      <ErrorBox error={err} />
    </div>
  )
}

function Steps({ steps }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Phase</th><th>Step</th><th>What happened</th><th className="right">Rows</th><th className="right">Time</th></tr></thead>
        <tbody>
          {steps.map((s, i) => (
            <tr key={i}>
              <td><span className="badge" style={{ color: PHASE[s.phase].color, borderColor: PHASE[s.phase].color }}>{PHASE[s.phase].label}</span></td>
              <td className="nowrap"><b>{s.name}</b></td>
              <td className="muted">{s.detail}</td>
              <td className="right mono">{s.rows === null ? '–' : num(s.rows)}</td>
              <td className="right mono">{s.seconds}s</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Etl({ data, reload, isAdmin }) {
  const etl = data?.etl
  const runs = data?.runs || []
  const last = runs[0]
  const live = etl?.running || (etl?.steps?.length && !last) ? etl.steps : null
  return (
    <div className="stack">
      <div className="grid g3">
        <div className="card">
          <span className="kicker" style={{ color: PHASE.extract.color }}>1 · Extract</span>
          <p className="muted" style={{ margin: 0 }}>
            Read data out of the source systems without changing them. <b>Full extraction</b> copies everything
            (the 5 raw day files and 3 cleaned split files). <b>Incremental extraction</b> copies only rows newer than
            a saved <b>watermark</b> (the last alert id loaded), which is how new portal alerts come in.
          </p>
        </div>
        <div className="card">
          <span className="kicker" style={{ color: PHASE.transform.color }}>2 · Transform</span>
          <p className="muted" style={{ margin: 0 }}>
            Make the data fit the warehouse: <b>integrate</b> sources (join flows to their raw timestamps),
            <b> clean</b> (missing or negative values), <b>derive</b> (bytes = forward + backward, µs → ms),
            <b> generalise</b> (port 80 → HTTP → well-known range) and assign <b>surrogate keys</b>.
          </p>
        </div>
        <div className="card">
          <span className="kicker" style={{ color: PHASE.load.color }}>3 · Load</span>
          <p className="muted" style={{ margin: 0 }}>
            Write into the warehouse. <b>Initial / full refresh</b> rebuilds everything in a staging file and swaps it
            in at once. <b>Incremental append</b> adds only new alerts. Small tables are <b>refreshed</b> (deleted and
            reloaded), and aggregates and marts are rebuilt after the facts.
          </p>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h3>Run the ETL job</h3>
          {isAdmin ? <EtlButtons state={etl} onStart={reload} built={data?.built} />
            : <span className="muted small">Only an administrator can run it.</span>}
        </div>
        <p className="muted small" style={{ margin: 0 }}>
          Tip for a demo: replay some traffic on the Administration page, then run an <b>incremental load</b>. Only the new alerts
          are extracted and appended, and the OLAP "Portal alerts" cube shows them.
        </p>
        {etl?.error && <div className="error" style={{ marginTop: 12 }}>{etl.error}</div>}
      </div>

      {etl?.running && (
        <div className="card pad-0 glow">
          <div className="card-head" style={{ padding: '16px 16px 0' }}>
            <h3><span className="pulse" style={{ display: 'inline-block', color: 'var(--accent)', marginRight: 8 }} />
              {etl.mode} load in progress</h3>
          </div>
          <Steps steps={etl.steps} />
        </div>
      )}

      {last && !etl?.running && (
        <div className="card pad-0">
          <div className="card-head" style={{ padding: '16px 16px 0' }}>
            <h3>Last run: {last.mode} load</h3>
            <span className="muted small">{new Date(last.finished_at).toLocaleString()} · watermark: alert id {last.alert_watermark}</span>
          </div>
          <Steps steps={last.steps} />
        </div>
      )}
      {live && !etl?.running && !last && <Steps steps={live} />}

      {runs.length > 0 && (
        <div className="card pad-0">
          <div className="card-head" style={{ padding: '16px 16px 0' }}><h3>Run history</h3></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th>Mode</th><th>Finished</th><th className="right">Steps</th><th className="right">Alert watermark</th><th className="right">Reviews</th><th className="right">Total time</th></tr></thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.run_id}>
                    <td className="mono">{r.run_id}</td><td>{r.mode}</td>
                    <td>{new Date(r.finished_at).toLocaleString()}</td>
                    <td className="right">{r.steps.length}</td>
                    <td className="right mono">{r.alert_watermark}</td>
                    <td className="right mono">{r.review_count}</td>
                    <td className="right mono">{r.steps.reduce((s, x) => s + x.seconds, 0).toFixed(1)}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="faint small" style={{ padding: '0 16px 16px', margin: 0 }}>
            Run history is kept inside the warehouse itself (table <code>etl_run</code>), so a full load starts a fresh history.
          </p>
        </div>
      )}
    </div>
  )
}
