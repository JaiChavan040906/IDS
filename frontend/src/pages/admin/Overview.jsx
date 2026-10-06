import { useEffect, useState } from 'react'
import { api, num } from '../../api'
import { Badge, ErrorBox, Meter, Stat, useApi } from '../../components/ui'

export default function Overview() {
  const { data: h, error, reload } = useApi(() => api('/admin/health'), [], 3000)
  const r = h?.replay
  return (
    <div className="stack">
      <ErrorBox error={error} />
      <div className="grid g4">
        <Stat label="Active model" value={h?.active_model || '–'} sub={h?.gpu ? `GPU: ${h.gpu}` : 'CPU inference'} />
        <Stat label="Alerts stored" value={num(h?.counts.alerts)} sub={`${num(h?.counts.feedback)} analyst decisions`} />
        <Stat label="Knowledge Repository" value={num(h?.counts.kr_entries)} sub="incidents" />
        <Stat label="Uptime" value={h ? fmtUptime(h.uptime_seconds) : '–'} sub={h ? `DB ${h.db_size_mb} MB` : ''} />
      </div>
      <div className="grid g2">
        <ReplayControl status={r} onChange={reload} />
        <div className="card">
          <h3>System health</h3>
          <div className="stack" style={{ gap: 14 }}>
            <div><div className="row between small"><span>Host CPU</span><span className="mono">{h?.cpu_percent ?? '–'}%</span></div><Meter value={(h?.cpu_percent || 0) / 100} /></div>
            <div><div className="row between small"><span>Host memory</span><span className="mono">{h?.memory_percent ?? '–'}%</span></div><Meter value={(h?.memory_percent || 0) / 100} color={h?.memory_percent > 85 ? 'red' : ''} /></div>
            <dl className="kv">
              <dt>API process</dt><dd>{h?.process_memory_mb} MB</dd>
              <dt>Retraining</dt><dd>{h?.retraining_busy ? <Badge kind="running"><span className="pulse" /> running</Badge> : 'idle'}</dd>
              <dt>Users</dt><dd>{h?.counts.users}</dd>
              <dt>Model versions</dt><dd>{h?.counts.model_versions}</dd>
            </dl>
          </div>
        </div>
      </div>
    </div>
  )
}

function fmtUptime(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return h ? `${h}h ${m}m` : `${m}m ${s % 60}s`
}

function ReplayControl({ status: r, onChange }) {
  const [cfg, setCfg] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    if (r && !cfg) setCfg({ mode: r.mode, batch_size: r.batch_size, interval_seconds: r.interval_seconds, attack_share: r.attack_share })
  }, [r, cfg])

  const act = async (action, extra = {}) => {
    setError(null)
    try { await api('/admin/replay', { method: 'POST', body: { action, ...extra } }); onChange() } catch (e) { setError(e) }
  }
  if (!r || !cfg) return <div className="card"><h3>Traffic replay</h3><p className="muted">Loading…</p></div>
  const set = (k, conv = (x) => x) => (e) => setCfg({ ...cfg, [k]: conv(e.target.value) })

  return (
    <div className="card stack">
      <div className="card-head" style={{ margin: 0 }}>
        <h3>Traffic replay</h3>
        {r.running ? <Badge kind="active"><span className="pulse" /> streaming</Badge> : <Badge>stopped</Badge>}
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        Replays the held-out test split through model <b>{r.model_version}</b>. The true labels stay hidden from the model and analysts.
      </p>
      <div>
        <div className="row between small"><span>Progress</span><span className="mono">{num(r.position)} / {num(r.total)}</span></div>
        <Meter value={r.position / Math.max(1, r.total)} />
      </div>
      <div className="grid g2">
        <label className="field">Mode
          <select value={cfg.mode} onChange={set('mode')}>
            <option value="attack_mix">Attack mix (demo)</option>
            <option value="sequential">Sequential (realistic)</option>
          </select>
        </label>
        <label className="field">Attack share (attack mix)
          <input type="number" step="0.05" min="0.05" max="0.95" value={cfg.attack_share ?? 0.3} onChange={set('attack_share', Number)} disabled={cfg.mode !== 'attack_mix'} />
        </label>
        <label className="field">Flows per tick
          <input type="number" min="1" max="2000" value={cfg.batch_size} onChange={set('batch_size', Number)} />
        </label>
        <label className="field">Seconds per tick
          <input type="number" step="0.1" min="0.1" max="60" value={cfg.interval_seconds} onChange={set('interval_seconds', Number)} />
        </label>
      </div>
      {r.last_error && <div className="error">Replay error: {r.last_error}</div>}
      <ErrorBox error={error} />
      <div className="row">
        {r.running
          ? <button className="btn danger" onClick={() => act('stop')}>Stop</button>
          : <button className="btn primary" onClick={() => act('start')}>Start replay</button>}
        <button className="btn" onClick={() => act('configure', cfg)}>Apply settings</button>
        <button className="btn ghost" onClick={() => act('reset')}>Reset to start</button>
      </div>
    </div>
  )
}
