import { useEffect, useRef, useState } from 'react'
import { api, apiUpload, num, pct } from '../../api'
import { Badge, ErrorBox, Meter, Stat, useApi } from '../../components/ui'
import { useFeatures } from '../../features'

export default function Overview() {
  const { data: h, error, reload } = useApi(() => api('/admin/health'), [], 3000)
  const sources = useApi(() => api('/admin/datasets'))
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
        <ReplayControl status={r} datasets={sources.data?.datasets} onChange={reload} />
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
              <dt>Warehouse tab</dt><dd><WarehouseSwitch /></dd>
            </dl>
          </div>
        </div>
      </div>
      <TrafficSources info={sources.data} current={r?.source} onChange={() => { sources.reload(); reload() }} />
    </div>
  )
}

// On/Off switch for the Warehouse tab (DWM practical). Off again whenever the portal restarts
// with start_portal.bat.
function WarehouseSwitch() {
  const { warehouse, setWarehouse } = useFeatures()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const flip = async (on) => {
    if (on === warehouse) return
    setBusy(true); setError(null)
    try { await setWarehouse(on) } catch (e) { setError(e) } finally { setBusy(false) }
  }
  return (
    <div>
      <div className="seg" role="group" aria-label="Warehouse tab">
        <button className={warehouse ? 'on benign' : ''} disabled={busy} onClick={() => flip(true)}>On</button>
        <button className={!warehouse ? 'on' : ''} disabled={busy} onClick={() => flip(false)}>Off</button>
      </div>
      <ErrorBox error={error} />
    </div>
  )
}

function fmtUptime(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return h ? `${h}h ${m}m` : `${m}m ${s % 60}s`
}

function ReplayControl({ status: r, datasets, onChange }) {
  const [cfg, setCfg] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    if (r && !cfg) setCfg({ source: r.source, mode: r.mode, batch_size: r.batch_size, interval_seconds: r.interval_seconds, attack_share: r.attack_share })
  }, [r, cfg])

  const act = async (action, extra = {}) => {
    setError(null)
    try { await api('/admin/replay', { method: 'POST', body: { action, ...extra } }); onChange() } catch (e) { setError(e) }
  }
  if (!r || !cfg) return <div className="card"><h3>Traffic replay</h3><p className="muted">Loading…</p></div>
  const set = (k, conv = (x) => x) => (e) => setCfg({ ...cfg, [k]: conv(e.target.value) })
  const chosen = datasets?.find((d) => d.id === cfg.source)
  const unlabelled = chosen ? !chosen.labelled : !r.labelled

  return (
    <div className="card stack">
      <div className="card-head" style={{ margin: 0 }}>
        <h3>Traffic replay</h3>
        {r.running ? <Badge kind="active"><span className="pulse" /> streaming</Badge> : <Badge>stopped</Badge>}
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        Plays <b>{r.source_name}</b> through model <b>{r.model_version}</b>.
        {r.labelled ? ' The true labels stay hidden from the model and analysts.' : ' This source has no labels, so only routing is measured.'}
      </p>
      <div>
        <div className="row between small"><span>Progress</span><span className="mono">{num(r.position)} / {num(r.total)}</span></div>
        <Meter value={r.position / Math.max(1, r.total)} />
      </div>
      <label className="field">Traffic source
        <select value={cfg.source} onChange={set('source')}>
          {datasets?.map((d) => (
            <option key={d.id} value={d.id}>{d.name}{d.rows_kept ? ` (${num(d.rows_kept)} flows${d.labelled ? '' : ', no labels'})` : ''}</option>
          ))}
        </select>
      </label>
      <div className="grid g2">
        <label className="field">Mode
          <select value={unlabelled ? 'sequential' : cfg.mode} onChange={set('mode')} disabled={unlabelled}>
            <option value="attack_mix">Attack mix (demo)</option>
            <option value="sequential">Sequential (realistic)</option>
          </select>
        </label>
        <label className="field">Attack share (attack mix)
          <input type="number" step="0.05" min="0.05" max="0.95" value={cfg.attack_share ?? 0.3} onChange={set('attack_share', Number)} disabled={unlabelled || cfg.mode !== 'attack_mix'} />
        </label>
        <label className="field">Flows per tick
          <input type="number" min="1" max="2000" value={cfg.batch_size} onChange={set('batch_size', Number)} />
        </label>
        <label className="field">Seconds per tick
          <input type="number" step="0.1" min="0.1" max="60" value={cfg.interval_seconds} onChange={set('interval_seconds', Number)} />
        </label>
      </div>
      {unlabelled && <p className="faint small" style={{ margin: 0 }}>Attack mix needs labels to know which flows are attacks, so unlabelled sources always play in order.</p>}
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

function TrafficSources({ info, current, onChange }) {
  const fileRef = useRef(null)
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [report, setReport] = useState(null)

  const upload = async () => {
    if (!file) return
    setBusy(true); setError(null); setReport(null)
    try {
      setReport(await apiUpload('/admin/datasets', file))
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
      onChange()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }
  const remove = async (id) => {
    setError(null)
    try { await api(`/admin/datasets/${id}`, { method: 'DELETE' }); onChange() } catch (e) { setError(e) }
  }
  const uploads = (info?.datasets || []).filter((d) => !d.built_in)

  return (
    <div className="card stack">
      <div className="card-head" style={{ margin: 0 }}><h3>Traffic sources</h3><span className="faint small">test the model on new data</span></div>
      <p className="muted small" style={{ margin: 0 }}>
        Upload a <b>CICFlowMeter CSV</b> (for example a day from CSE-CIC-IDS2018, or flows you captured yourself) to replay it
        instead of our test split. Column names are matched automatically. A <span className="mono">Label</span> column is optional
        and is used only for evaluation. Files over {num(info?.max_rows)} flows are randomly sampled. Limit {info?.max_upload_mb} MB.
      </p>
      <div className="row">
        <input ref={fileRef} type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] || null)} style={{ maxWidth: 360 }} />
        <button className="btn primary" disabled={!file || busy} onClick={upload}>{busy ? 'Importing… large files take a minute' : 'Upload and import'}</button>
      </div>
      <ErrorBox error={error} />
      {report && <ImportReport m={report} />}
      {uploads.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th className="right">Flows</th><th>Labels</th><th>Measurements</th><th>Imported</th><th /></tr></thead>
            <tbody>
              {uploads.map((d) => (
                <tr key={d.id}>
                  <td><b>{d.name}</b>{d.id === current && <> <Badge kind="active">in replay</Badge></>}<div className="faint small mono">{d.file}</div></td>
                  <td className="right mono">{num(d.rows_kept)}{d.sampled && <div className="faint small">of {num(d.rows_in_file)}</div>}</td>
                  <td>{d.labelled ? <Badge kind="verified">labelled</Badge> : <Badge>none</Badge>}{d.attack_share != null && <div className="faint small">{pct(d.attack_share, 1)} attacks</div>}</td>
                  <td>{d.features_found}/{d.features_total}{d.features_missing?.length > 0 && <div className="faint small">{d.features_missing.length} filled with typical values</div>}</td>
                  <td className="small faint">{new Date(d.created_at).toLocaleString()}</td>
                  <td><button className="btn sm ghost" disabled={d.id === current} onClick={() => remove(d.id)}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="faint small" style={{ margin: 0 }}>After importing, pick it under <b>Traffic source</b> above, press <b>Apply settings</b>, then <b>Start replay</b>. Results appear per source on the Evaluation tab.</p>
    </div>
  )
}

function ImportReport({ m }) {
  const labels = Object.entries(m.label_counts || {})
  return (
    <div className={`${m.quality === 'good' ? 'success' : 'note'} stack`} style={{ gap: 6 }}>
      {m.quality_note && <b>Warning: {m.quality_note}</b>}
      <b>Imported &quot;{m.name}&quot;: {num(m.rows_kept)} flows{m.sampled ? ` (random sample of ${num(m.rows_in_file)})` : ''}.</b>
      <span>Matched {m.features_found} of {m.features_total} measurements{m.features_missing.length ? `; filled with typical values: ${m.features_missing.join(', ')}` : ''}.</span>
      {m.columns_ignored?.length > 0 && <span>Ignored {m.columns_ignored.length} of the file&apos;s {m.columns_in_file} columns that the model does not use.</span>}
      <span>{m.labelled ? `Labels: ${labels.map(([k, v]) => `${k} ${num(v)}`).join(' · ')}` : 'No Label column: the replay will measure routing only.'}</span>
      {m.unmapped_labels?.length > 0 && <span>Attack types the model was never trained on (counted as attacks): {m.unmapped_labels.join(', ')}</span>}
    </div>
  )
}
