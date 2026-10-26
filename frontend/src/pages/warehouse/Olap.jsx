import { useEffect, useMemo, useState } from 'react'
import { api, num } from '../../api'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { OTHER, SERIES } from '../../components/charts'
import { Empty, ErrorBox, useApi } from '../../components/ui'
import Cube3D from './Cube3D'

const DEFAULTS = {
  flows: { measure: 'flows', rows: { dim: 'time', level: 'day' }, cols: { dim: 'attack', level: 'category' }, filters: [] },
  alerts: { measure: 'alerts', rows: { dim: 'route', level: 'route' }, cols: { dim: 'attack', level: 'category' }, filters: [] },
}

// Ready-made examples, one per OLAP operation, for a quick demo.
const PRESETS = [
  { name: 'Start: flows per day × attack category', op: 'start', cube: 'flows',
    state: DEFAULTS.flows },
  { name: 'Drill-down: Wednesday by hour', op: 'drill-down', cube: 'flows',
    state: { measure: 'flows', rows: { dim: 'time', level: 'hour' }, cols: { dim: 'attack', level: 'category' },
      filters: [{ dim: 'time', level: 'day', values: ['Wed 05 Jul 2017'] }] } },
  { name: 'Roll-up: benign vs malicious per day', op: 'roll-up', cube: 'flows',
    state: { measure: 'flows', rows: { dim: 'time', level: 'day' }, cols: { dim: 'attack', level: 'nature' }, filters: [] } },
  { name: 'Slice: only HTTP traffic', op: 'slice', cube: 'flows',
    state: { measure: 'flows', rows: { dim: 'time', level: 'day' }, cols: { dim: 'attack', level: 'attack_class' },
      filters: [{ dim: 'service', level: 'service', values: ['HTTP'] }] } },
  { name: 'Dice: DoS on Wed + Thu, HTTP/HTTPS', op: 'dice', cube: 'flows',
    state: { measure: 'bytes', rows: { dim: 'attack', level: 'attack_class' }, cols: { dim: 'service', level: 'service' },
      filters: [{ dim: 'time', level: 'day', values: ['Wed 05 Jul 2017', 'Thu 06 Jul 2017'] },
        { dim: 'attack', level: 'category', values: ['Denial of service', 'Distributed DoS'] },
        { dim: 'service', level: 'service', values: ['HTTP', 'HTTPS'] }] } },
  { name: 'Pivot: services as rows, protocols as columns', op: 'pivot', cube: 'flows',
    state: { measure: 'flows', rows: { dim: 'service', level: 'port_range' }, cols: { dim: 'protocol', level: 'protocol' }, filters: [] } },
]

const OP_STYLE = { start: '', 'roll-up': 'approved', 'drill-down': 'benign', slice: 'review', dice: 'medium', pivot: 'analyst' }

export default function Olap({ built }) {
  const meta = useApi(() => api('/dw/meta'), [])
  const [cube, setCube] = useState('flows')
  const [q, setQ] = useState(DEFAULTS.flows)
  const [history, setHistory] = useState([{ op: 'start', text: 'Flows per day × attack category' }])
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [depthPick, setDepthPick] = useState(null)      // 3rd (depth) dimension of the 3-D cube
  const [cubeRes, setCubeRes] = useState(null)
  const [cubeErr, setCubeErr] = useState(null)

  const c = meta.data?.[cube]
  const dims = useMemo(() => Object.fromEntries((c?.dims || []).map((d) => [d.id, d])), [c])
  const levelIdx = (dim, level) => dims[dim]?.levels.findIndex((l) => l.id === level) ?? -1
  const levelLabel = (dim, level) => dims[dim]?.levels.find((l) => l.id === level)?.label || level
  const dimLabel = (dim) => dims[dim]?.label || dim

  useEffect(() => {
    if (!built || !c) return undefined
    let stale = false
    setBusy(true)
    api('/dw/olap', { method: 'POST', body: { cube, ...q } })
      .then((r) => { if (!stale) { setRes(r); setErr(null) } })
      .catch((e) => { if (!stale) setErr(e) })
      .finally(() => { if (!stale) setBusy(false) })
    return () => { stale = true }
  }, [built, c, cube, q])

  // depth axis: the user's pick if it is free, else the first free dimension in this order
  const used = new Set([q.rows?.dim, q.cols?.dim])
  const prefer = cube === 'flows' ? ['protocol', 'split', 'attack', 'time', 'service'] : ['severity', 'route', 'source', 'model', 'attack', 'time']
  const depthDim = depthPick && !used.has(depthPick.dim) && dims[depthPick.dim] ? depthPick.dim
    : prefer.find((d) => dims[d] && !used.has(d))
  const depth = depthDim ? { dim: depthDim, level: depthPick?.dim === depthDim ? depthPick.level : dims[depthDim].levels[0].id } : null

  useEffect(() => {
    if (!built || !c || !q.cols || !depth) { setCubeRes(null); return undefined }
    let stale = false
    api('/dw/cube', { method: 'POST', body: { cube, measure: q.measure, x: q.cols, y: q.rows, z: depth, filters: q.filters } })
      .then((r) => { if (!stale) { setCubeRes(r); setCubeErr(null) } })
      .catch((e) => { if (!stale) setCubeErr(e) })
    return () => { stale = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [built, c, cube, q, depth?.dim, depth?.level])

  if (!built) return <Empty title="Build the warehouse first">An administrator builds it once from the Warehouse page.</Empty>

  const log = (op, text) => setHistory((h) => [...h.slice(-9), { op, text }])
  const apply = (next, op, text) => { setQ(next); log(op, text) }

  const move = (axis, step) => {
    const a = q[axis]
    const i = levelIdx(a.dim, a.level) + step
    const levels = dims[a.dim].levels
    if (i < 0 || i >= levels.length) return
    const level = levels[i].id
    let filters = q.filters
    if (step < 0) filters = filters.filter((f) => f.dim !== a.dim || levelIdx(f.dim, f.level) < i)
    apply({ ...q, [axis]: { ...a, level }, filters }, step < 0 ? 'roll-up' : 'drill-down',
      `${dimLabel(a.dim)}: ${levelLabel(a.dim, a.level)} → ${levels[i].label}`)
  }

  const drillInto = (member) => {
    const a = q.rows
    const i = levelIdx(a.dim, a.level)
    const levels = dims[a.dim].levels
    if (i >= levels.length - 1 || member === '(none)') return
    const filters = [...q.filters.filter((f) => !(f.dim === a.dim && f.level === a.level)),
      { dim: a.dim, level: a.level, values: [member] }]
    apply({ ...q, rows: { ...a, level: levels[i + 1].id }, filters }, 'drill-down',
      `into “${member}” → ${levels[i + 1].label}`)
  }

  const pivot = () => {
    if (!q.cols) return
    apply({ ...q, rows: q.cols, cols: q.rows }, 'pivot',
      `rows ${dimLabel(q.rows.dim)} ↔ columns ${dimLabel(q.cols.dim)}`)
  }

  const setAxis = (axis, dim) => {
    if (axis === 'cols' && !dim) return apply({ ...q, cols: null }, 'start', 'Columns removed')
    const next = { ...q, [axis]: { dim, level: dims[dim].levels[0].id } }
    if (axis === 'rows' && q.cols?.dim === dim) next.cols = null   // rows and columns must differ
    return apply(next, 'start', `${axis === 'rows' ? 'Rows' : 'Columns'}: ${dimLabel(dim)}`)
  }

  const filterDims = new Set(q.filters.map((f) => f.dim))
  const kind = filterDims.size === 0 ? null : filterDims.size === 1 ? 'Slice' : 'Dice'

  const max = res ? Math.max(1, ...res.cells.flat().filter((v) => typeof v === 'number')) : 1
  const rowTotals = res?.cells.map((r) => r.reduce((s, v) => s + (v || 0), 0))
  const colTotals = res?.cols.map((_, j) => res.cells.reduce((s, r) => s + (r[j] || 0), 0))
  const fmt = (v) => (v === null || v === undefined ? '' : typeof v === 'number' && !Number.isInteger(v) ? v.toLocaleString(undefined, { maximumFractionDigits: 4 }) : num(v))
  const canDrill = q.rows && levelIdx(q.rows.dim, q.rows.level) < (dims[q.rows.dim]?.levels.length || 0) - 1

  return (
    <div className="stack">
      <div className="note">
        <b>OLAP cube</b>: pick what to measure and how to group it. <b>Roll-up</b> = coarser level, <b>drill-down</b> = finer
        level (or click a row name), <b>slice</b> = filter one dimension, <b>dice</b> = filter two or more, <b>pivot</b> = swap
        rows and columns. Watch the cube, the table and the chart change with each operation.
      </div>
      <ErrorBox error={meta.error} />

      <div className="card">
        <div className="row" style={{ gap: 8, marginBottom: 12 }}>
          <span className="muted small">Examples:</span>
          {PRESETS.filter((p) => p.cube === cube).map((p) => (
            <button key={p.name} className="btn sm" onClick={() => apply(p.state, p.op, p.name)}>
              <span className={`badge ${OP_STYLE[p.op]}`}>{p.op}</span>{p.name.split(': ')[1] || p.name}
            </button>
          ))}
        </div>
        <div className="grid g4" style={{ alignItems: 'end' }}>
          <label className="field">Cube (fact table)
            <select value={cube} onChange={(e) => { setCube(e.target.value); setQ(DEFAULTS[e.target.value]); setHistory([{ op: 'start', text: `Cube: ${meta.data[e.target.value].label}` }]) }}>
              {meta.data && Object.entries(meta.data).map(([k, v]) => <option key={k} value={k}>{v.label} ({v.fact})</option>)}
            </select>
          </label>
          <label className="field">Measure
            <select value={q.measure} onChange={(e) => apply({ ...q, measure: e.target.value }, 'start', `Measure: ${e.target.selectedOptions[0].text}`)}>
              {c?.measures.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </label>
          <AxisPicker label="Rows" axis={q.rows} dims={c?.dims} onDim={(d) => setAxis('rows', d)}
            onUp={() => move('rows', -1)} onDown={() => move('rows', 1)} levelIdx={levelIdx} />
          <AxisPicker label="Columns" axis={q.cols} dims={c?.dims} optional exclude={q.rows.dim}
            onDim={(d) => setAxis('cols', d)} onUp={() => move('cols', -1)} onDown={() => move('cols', 1)} levelIdx={levelIdx} />
        </div>
        <div className="row" style={{ marginTop: 14, gap: 10 }}>
          <button className="btn sm" onClick={pivot} disabled={!q.cols}>⇄ Pivot</button>
          <FilterAdder cube={cube} dims={c?.dims || []} onAdd={(f) => {
            const filters = [...q.filters.filter((x) => !(x.dim === f.dim && x.level === f.level)), f]
            const n = new Set(filters.map((x) => x.dim)).size
            apply({ ...q, filters }, n > 1 ? 'dice' : 'slice', `${dimLabel(f.dim)} · ${levelLabel(f.dim, f.level)} = ${f.values.join(', ')}`)
          }} />
          {kind && <span className={`badge ${kind === 'Slice' ? 'review' : 'medium'}`}>{kind}</span>}
          {q.filters.map((f) => (
            <span key={`${f.dim}-${f.level}`} className="badge" title="Remove filter">
              {dimLabel(f.dim)} · {levelLabel(f.dim, f.level)} = {f.values.join(', ')}
              <button className="btn sm ghost" style={{ padding: '0 4px' }}
                onClick={() => apply({ ...q, filters: q.filters.filter((x) => x !== f) }, 'start', `Removed filter on ${dimLabel(f.dim)}`)}>×</button>
            </span>
          ))}
        </div>
      </div>

      <CubeCard cubeRes={cubeRes} cubeErr={cubeErr} hasCols={!!q.cols} depth={depth} dims={dims} used={used}
        fmt={fmt} onDepth={(d) => { setDepthPick(d); log('start', `Cube depth: ${dimLabel(d.dim)} (${levelLabel(d.dim, d.level)})`) }} />

      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 3fr) minmax(0, 1fr)' }}>
        <div className="card pad-0">
          <div className="card-head" style={{ padding: '16px 16px 0' }}>
            <h3>
              {c?.measures.find((m) => m.id === q.measure)?.label} by {dimLabel(q.rows.dim)} ({levelLabel(q.rows.dim, q.rows.level)})
              {q.cols && <> × {dimLabel(q.cols.dim)} ({levelLabel(q.cols.dim, q.cols.level)})</>}
            </h3>
            <span className="muted small nowrap">{busy ? 'running…' : res && <>{res.ms} ms · <code>{res.source}</code></>}</span>
          </div>
          {res?.used_aggregate && (
            <div className="success" style={{ margin: '0 16px 10px' }}>
              Answered from the <b>aggregate table</b> agg_flow_hour instead of 1.7 million flows (aggregate navigator).
            </div>
          )}
          <ErrorBox error={err} />
          {res && (
            <div className="table-wrap" style={{ maxHeight: 560, overflowY: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th>{levelLabel(q.rows.dim, q.rows.level)}</th>
                    {(res.cols.length ? res.cols : ['value']).map((cname) => (
                      <th key={cname} className="right" style={{ textTransform: 'none' }}>{res.cols.length ? cname : c?.measures.find((m) => m.id === q.measure)?.label}</th>
                    ))}
                    {res.additive && res.cols.length > 1 && <th className="right">Total</th>}
                  </tr>
                </thead>
                <tbody>
                  {res.rows.map((r, i) => (
                    <tr key={r}>
                      <td className="nowrap">
                        {canDrill
                          ? <a href="#" onClick={(e) => { e.preventDefault(); drillInto(r) }} title="Drill down into this member">{r} ▾</a>
                          : r}
                      </td>
                      {res.cells[i].map((v, j) => (
                        <td key={j} className="right mono" style={{ background: typeof v === 'number' ? `rgba(61, 252, 156, ${(0.04 + 0.32 * v / max).toFixed(3)})` : undefined }}>{fmt(v)}</td>
                      ))}
                      {res.additive && res.cols.length > 1 && <td className="right mono"><b>{fmt(rowTotals[i])}</b></td>}
                    </tr>
                  ))}
                  {res.additive && res.rows.length > 1 && (
                    <tr>
                      <td><b>Total</b></td>
                      {colTotals.map((v, j) => <td key={j} className="right mono"><b>{fmt(v)}</b></td>)}
                      {res.cols.length > 1 && <td className="right mono"><b>{fmt(colTotals.reduce((a, b) => a + b, 0))}</b></td>}
                    </tr>
                  )}
                  {!res.rows.length && <tr><td className="muted">No data for this selection.</td></tr>}
                </tbody>
              </table>
            </div>
          )}
          {res?.note && <p className="faint small" style={{ padding: '8px 16px', margin: 0 }}>{res.note}</p>}
          {res && !res.additive && <p className="faint small" style={{ padding: '8px 16px', margin: 0 }}>Averages are not added up, so no totals are shown.</p>}
        </div>
        <div className="card">
          <h3>Operations applied</h3>
          <ol style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 6 }}>
            {history.map((h, i) => (
              <li key={i} className="small"><span className={`badge ${OP_STYLE[h.op]}`}>{h.op}</span> <span className="muted">{h.text}</span></li>
            ))}
          </ol>
        </div>
      </div>

      {res && res.rows.length > 0 && <ResultChart res={res} fmt={fmt} measure={c?.measures.find((m) => m.id === q.measure)?.label}
        rowsLabel={levelLabel(q.rows.dim, q.rows.level)} />}
    </div>
  )
}

function AxisPicker({ label, axis, dims, optional, exclude, onDim, onUp, onDown, levelIdx }) {
  const d = dims?.find((x) => x.id === axis?.dim)
  const i = axis ? levelIdx(axis.dim, axis.level) : -1
  return (
    <label className="field">{label}{axis && d && <span className="hint">level: {d.levels[i]?.label}</span>}
      <div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
        <select value={axis?.dim || ''} onChange={(e) => onDim(e.target.value)}>
          {optional && <option value="">(none)</option>}
          {dims?.filter((x) => x.id !== exclude).map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
        </select>
        <button type="button" className="btn sm" title="Roll up (coarser level)" disabled={!axis || i <= 0} onClick={onUp}>▲</button>
        <button type="button" className="btn sm" title="Drill down (finer level)" disabled={!axis || !d || i >= d.levels.length - 1} onClick={onDown}>▼</button>
      </div>
    </label>
  )
}

function FilterAdder({ cube, dims, onAdd }) {
  const [open, setOpen] = useState(false)
  const [dim, setDim] = useState('')
  const [level, setLevel] = useState('')
  const [values, setValues] = useState([])
  const [search, setSearch] = useState('')
  const d = dims.find((x) => x.id === dim)
  const members = useApi(() => (dim && level ? api('/dw/members', { params: { cube, dim, level } }) : Promise.resolve([])), [cube, dim, level])
  if (!open) return <button className="btn sm" onClick={() => setOpen(true)}>+ Slice / dice filter</button>
  const shown = (members.data || []).filter((m) => m.toLowerCase().includes(search.toLowerCase())).slice(0, 200)
  return (
    <div className="card" style={{ padding: 12, width: '100%' }}>
      <div className="row" style={{ gap: 8 }}>
        <select style={{ width: 'auto' }} value={dim} onChange={(e) => { setDim(e.target.value); setLevel(dims.find((x) => x.id === e.target.value)?.levels[0].id || ''); setValues([]) }}>
          <option value="">Dimension…</option>
          {dims.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
        </select>
        {d && (
          <select style={{ width: 'auto' }} value={level} onChange={(e) => { setLevel(e.target.value); setValues([]) }}>
            {d.levels.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
          </select>
        )}
        {d && <input style={{ width: 180 }} placeholder="Search values" value={search} onChange={(e) => setSearch(e.target.value)} />}
        <div className="spacer" style={{ flex: 1 }} />
        <button className="btn sm primary" disabled={!values.length} onClick={() => { onAdd({ dim, level, values }); setOpen(false); setValues([]); setDim(''); setSearch('') }}>Apply filter</button>
        <button className="btn sm ghost" onClick={() => setOpen(false)}>Cancel</button>
      </div>
      {d && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10, maxHeight: 160, overflowY: 'auto' }}>
          {shown.map((m) => {
            const on = values.includes(m)
            return (
              <button key={m} className={`badge ${on ? 'benign' : ''}`} style={{ cursor: 'pointer' }}
                onClick={() => setValues((v) => (on ? v.filter((x) => x !== m) : [...v, m]))}>{on ? '✓ ' : ''}{m}</button>
            )
          })}
          {members.loading && <span className="muted small">loading…</span>}
        </div>
      )}
      <p className="faint small" style={{ margin: '8px 0 0' }}>One value on one dimension = slice. Filters on two or more dimensions = dice.</p>
    </div>
  )
}

// ---------------------------------------------------------------- the 3-D cube card
function CubeCard({ cubeRes, cubeErr, hasCols, depth, dims, used, fmt, onDepth }) {
  const free = Object.values(dims).filter((d) => !used.has(d.id))
  const d = depth && dims[depth.dim]
  const li = d ? d.levels.findIndex((l) => l.id === depth.level) : -1
  const hl = cubeRes?.highlight || {}
  return (
    <div className="card">
      <div className="card-head">
        <h3>The cube</h3>
        <span className="muted small">{cubeRes && <>{cubeRes.ms} ms · <code>{cubeRes.source}</code></>}</span>
      </div>
      <ErrorBox error={cubeErr} />
      {!hasCols && <p className="muted" style={{ margin: 0 }}>Choose a <b>Columns</b> dimension to see the data as a 3-D cube.</p>}
      {hasCols && (
        <div className="cube-wrap">
          <div>{cubeRes ? <Cube3D cube={cubeRes} fmt={fmt} /> : <p className="muted">Building the cube…</p>}</div>
          <div className="stack" style={{ gap: 12 }}>
            <p className="small muted" style={{ margin: 0 }}>
              Three dimensions at once: <b>X</b> = Columns, <b>Y</b> = Rows, <b>Z</b> = depth. Each block is one cell;
              brighter blocks hold larger values. The table below is one face of this cube, added up along Z.
            </p>
            <label className="field">Depth (Z axis)
              <div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                <select value={depth?.dim || ''} onChange={(e) => onDepth({ dim: e.target.value, level: dims[e.target.value].levels[0].id })}>
                  {free.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
                </select>
                <button type="button" className="btn sm" title="Roll up (coarser)" disabled={li <= 0} onClick={() => onDepth({ dim: depth.dim, level: d.levels[li - 1].id })}>▲</button>
                <button type="button" className="btn sm" title="Drill down (finer)" disabled={!d || li >= d.levels.length - 1} onClick={() => onDepth({ dim: depth.dim, level: d.levels[li + 1].id })}>▼</button>
              </div>
              {d && <span className="hint">level: {d.levels[li]?.label}</span>}
            </label>
            <div className="small">
              <div className="muted" style={{ marginBottom: 4 }}>What each operation does to the cube</div>
              <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 3 }} className="muted">
                <li><b>Drill-down / roll-up</b>: an axis gets more / fewer blocks</li>
                <li><b>Slice</b>: one layer lights up (filter one axis)</li>
                <li><b>Dice</b>: a smaller block of blocks lights up (filter 2+ axes)</li>
                <li><b>Pivot</b>: X and Y swap, the cube turns</li>
              </ul>
            </div>
            {Object.keys(hl).length > 0 && (
              <div className="note small" style={{ margin: 0 }}>
                Lit blocks = your {Object.keys(hl).length > 1 ? 'dice' : 'slice'} ({Object.entries(hl).map(([i, v]) => `${cubeRes.axes[i].dim_label} = ${v.join(', ')}`).join('; ')}); faded blocks = the rest of the cube.
              </div>
            )}
            {cubeRes?.axes.some((a) => a.dropped) && (
              <p className="faint small" style={{ margin: 0 }}>
                Showing the 8 largest members per axis ({cubeRes.axes.filter((a) => a.dropped).map((a) => `${a.dropped} more ${a.dim_label}`).join(', ')} hidden).
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- same result as a chart
const tooltipStyle = { background: '#0e141d', border: '1px solid #2a3747', borderRadius: 10, fontSize: 12 }

function ResultChart({ res, fmt, measure, rowsLabel }) {
  const cols = res.cols.length ? res.cols : ['value']
  // up to 8 series in the fixed palette order (7 + "Other" when there are more)
  const ranked = cols.map((cname, j) => [cname, res.cells.reduce((s, r) => s + Math.abs(r[j] || 0), 0)])
    .sort((a, b) => b[1] - a[1])
  const keep = new Set(ranked.slice(0, cols.length > 8 ? 7 : 8).map((x) => x[0]))
  const series = cols.filter((cname) => keep.has(cname))
  const hasOther = series.length < cols.length && res.additive
  const rows = res.rows.slice(0, 40)
  const data = rows.map((r, i) => {
    const o = { row: String(r).replace(/ 20\d\d/, '') }
    cols.forEach((cname, j) => {
      const v = res.cells[i][j] || 0
      if (keep.has(cname)) o[cname] = v
      else if (hasOther) o.Other = (o.Other || 0) + v
    })
    return o
  })
  const stacked = res.additive && cols.length > 1
  return (
    <div className="card">
      <div className="card-head">
        <h3>The same result as a chart</h3>
        <span className="faint small">{measure} by {rowsLabel}{stacked ? ', stacked by column' : ''}{res.rows.length > 40 ? ` · first 40 of ${res.rows.length} rows` : ''}</span>
      </div>
      <div style={{ height: 320 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ left: 10, right: 10, bottom: 10 }}>
            <CartesianGrid stroke="#1d2733" vertical={false} />
            <XAxis dataKey="row" stroke="#5d6a7b" fontSize={11} interval={0} angle={rows.length > 6 ? -25 : 0}
              textAnchor={rows.length > 6 ? 'end' : 'middle'} height={rows.length > 6 ? 70 : 30} />
            <YAxis stroke="#5d6a7b" fontSize={11} width={70}
              tickFormatter={(v) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e3 ? `${Math.round(v / 1e3)}k` : v)} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(255,255,255,.03)' }} formatter={(v) => fmt(v)} />
            {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
            {series.map((cname, i) => (
              <Bar key={cname} dataKey={cname} name={cname === 'value' ? measure : cname} stackId={stacked ? 'a' : undefined}
                fill={SERIES[i]} stroke="#0e141d" strokeWidth={stacked ? 2 : 0} radius={stacked ? 0 : [4, 4, 0, 0]} />
            ))}
            {hasOther && <Bar dataKey="Other" stackId={stacked ? 'a' : undefined} fill={OTHER} stroke="#0e141d" strokeWidth={2} />}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
