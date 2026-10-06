import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, num, pct } from '../../api'
import { ErrorBox, Stat, useApi } from '../../components/ui'

const WINDOWS = [[15, '15 min'], [60, '1 hour'], [1440, '24 hours']]
const tooltipStyle = { background: '#0e141d', border: '1px solid #2a3747', borderRadius: 10, fontSize: 12 }

export default function Dashboard() {
  const [minutes, setMinutes] = useState(60)
  const { data, error } = useApi(() => api('/stats/overview', { params: { minutes } }), [minutes], 5000)
  const byClass = Object.entries(data?.alerts_by_class || {})
    .map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count)
  const sev = (d, s) => data?.open_queue?.find((q) => q.decision === d && q.severity === s)?.count || 0
  const timeline = (data?.timeline || []).map((p) => ({ ...p, t: new Date(p.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }))

  return (
    <div className="stack">
      <ErrorBox error={error} />
      <div className="row between">
        <span className="muted">Live traffic · refreshes every 5 s</span>
        <div className="seg">
          {WINDOWS.map(([m, l]) => <button key={m} className={minutes === m ? 'on' : ''} onClick={() => setMinutes(m)}>{l}</button>)}
        </div>
      </div>
      <div className="grid g4">
        <Stat label="Flows scored" value={num(data?.flows)} sub={data ? `${data.ms_per_flow} ms per flow` : ''} />
        <Stat label="Auto-closed benign" value={num(data?.auto_benign)} sub={data?.flows ? pct(data.auto_benign / data.flows, 1) : ''} />
        <Stat label="Confident alerts" value={num(data?.auto_alert)} sub={data?.flows ? pct(data.auto_alert / data.flows, 1) : ''} />
        <Stat label="Sent to review" value={num(data?.review)} sub={data?.flows ? pct(data.review / data.flows, 1) : ''} />
      </div>
      <div className="grid g3">
        <div className="card span2">
          <div className="card-head"><h3>Traffic</h3><span className="faint small">flows / alerts / review per interval</span></div>
          <div style={{ height: 240 }}>
            <ResponsiveContainer>
              <AreaChart data={timeline}>
                <CartesianGrid stroke="#1d2733" vertical={false} />
                <XAxis dataKey="t" stroke="#5d6a7b" fontSize={11} minTickGap={40} />
                <YAxis stroke="#5d6a7b" fontSize={11} width={40} />
                <Tooltip contentStyle={tooltipStyle} />
                <Area type="monotone" dataKey="flows" stroke="#6c8cff" fill="rgba(108,140,255,.15)" />
                <Area type="monotone" dataKey="alerts" stroke="#ff5d6e" fill="rgba(255,93,110,.15)" />
                <Area type="monotone" dataKey="review" stroke="#ffb547" fill="rgba(255,181,71,.18)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <h3>Open work</h3>
          <table>
            <thead><tr><th /><th className="right">Review</th><th className="right">Alerts</th></tr></thead>
            <tbody>
              {['high', 'medium', 'low'].map((s) => (
                <tr key={s}><td><span className={`badge ${s}`}>{s}</span></td>
                  <td className="right">{sev('review', s)}</td><td className="right">{sev('auto_alert', s)}</td></tr>
              ))}
            </tbody>
          </table>
          <div className="row" style={{ marginTop: 16 }}>
            <Link className="btn primary sm" to="/analyst/review">Open review queue</Link>
          </div>
          <p className="faint small" style={{ marginTop: 14 }}>
            {num(data?.reviewed_total)} decisions recorded · {num(data?.kr_total)} KR entries
          </p>
        </div>
      </div>
      <div className="card">
        <div className="card-head"><h3>Alerts by predicted class</h3></div>
        {byClass.length ? (
          <div style={{ height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={byClass} layout="vertical" margin={{ left: 40 }}>
                <CartesianGrid stroke="#1d2733" horizontal={false} />
                <XAxis type="number" stroke="#5d6a7b" fontSize={11} />
                <YAxis type="category" dataKey="name" stroke="#8a97a8" fontSize={12} width={120} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(255,255,255,.03)' }} />
                <Bar dataKey="count" fill="#3dfc9c" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : <p className="muted">No alerts in this window. An administrator can start the traffic replay.</p>}
      </div>
    </div>
  )
}
