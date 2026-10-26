import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, num } from '../../api'
import { BarList, SERIES, useVisual } from '../../components/charts'
import { Stat, useApi } from '../../components/ui'

const tooltipStyle = { background: '#0e141d', border: '1px solid #2a3747', borderRadius: 10, fontSize: 12 }
const olap = (body) => api('/dw/olap', { method: 'POST', body: { cube: 'flows', measure: 'flows', ...body } })

export default function Overview({ data }) {
  const visual = useVisual()
  const tables = data?.tables || []
  const rows = (n) => tables.find((t) => t.name === n)?.rows
  const built = data?.built
  // two small summaries, answered from the pre-summed aggregate table (about 1 ms each)
  const perDay = useApi(() => (built ? olap({ rows: { dim: 'time', level: 'day' }, cols: { dim: 'attack', level: 'nature' } })
    : Promise.resolve(null)), [built])
  const perCat = useApi(() => (built ? olap({ rows: { dim: 'attack', level: 'category' },
    filters: [{ dim: 'attack', level: 'nature', values: ['Malicious'] }] }) : Promise.resolve(null)), [built])

  const dayData = perDay.data?.rows.map((r, i) => {
    const row = { day: r.replace(/ 20\d\d$/, '') }
    perDay.data.cols.forEach((c, j) => { row[c] = perDay.data.cells[i][j] || 0 })
    return row
  }) || []
  const catItems = perCat.data?.rows.map((r, i) => ({ label: r, value: perCat.data.cells[i][0] || 0 }))
    .sort((a, b) => b.value - a.value) || []
  const malicious = catItems.reduce((s, d) => s + d.value, 0)

  return (
    <div className="stack">
      {built && (
        <div className="grid g4">
          <Stat label="Flows in the fact table" value={num(rows('fact_flow'))} sub="grain: one network flow" />
          <Stat label="Attack flows" value={num(malicious || null)} sub={rows('fact_flow') && malicious ? `${((100 * malicious) / rows('fact_flow')).toFixed(1)}% of all flows` : ''} />
          <Stat label="Tables" value={tables.length} sub="facts, dimensions, aggregate, marts" />
          <Stat label="Warehouse size" value={`${data.warehouse_mb} MB`} sub={data.warehouse_path} />
        </div>
      )}

      <div className="card">
        <h3>Architecture: how data reaches the warehouse</h3>
        <div className="flow-diagram" style={{ marginTop: 8 }}>
          <div className="node"><b>Sources</b><span>5 raw day CSVs<br />3 cleaned split files<br />portal DB (ids.db)</span></div>
          <div className="arrow">→</div>
          <div className="node"><b>ETL + staging</b><span>extract, clean, derive,<br />assign keys in<br />warehouse.db.staging</span></div>
          <div className="arrow">→</div>
          <div className="node" style={{ borderColor: 'var(--accent)' }}><b>Data warehouse</b><span>star, snowflake and<br />constellation schemas<br />warehouse.db</span></div>
          <div className="arrow">→</div>
          <div className="node"><b>Data marts</b><span>threat analysis<br />security operations</span></div>
          <div className="arrow">→</div>
          <div className="node"><b>OLAP + reports</b><span>roll-up, drill-down,<br />slice, dice, pivot</span></div>
        </div>
        <p className="muted small" style={{ marginTop: 14, marginBottom: 0 }}>
          The data is copied in by an ETL job, then only read. The detection model and the analyst never use it, so
          analysis here cannot change a detection.
          {data?.span?.length === 2 && <> Traffic covered: {data.span[0]} to {data.span[1]} (dataset clock).</>}
        </p>
      </div>

      {built && visual && (
        <div className="grid g2">
          <div className="card">
            <div className="card-head"><h3>What the warehouse holds: flows per day</h3><span className="faint small">benign vs malicious</span></div>
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={dayData} margin={{ left: 10, right: 10 }}>
                  <CartesianGrid stroke="#1d2733" vertical={false} />
                  <XAxis dataKey="day" stroke="#5d6a7b" fontSize={11} />
                  <YAxis stroke="#5d6a7b" fontSize={11} width={60} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(255,255,255,.03)' }} formatter={(v) => num(v)} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="Benign" stackId="a" fill={SERIES[0]} stroke="#0e141d" strokeWidth={2} />
                  <Bar dataKey="Malicious" stackId="a" fill={SERIES[1]} stroke="#0e141d" strokeWidth={2} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="faint small" style={{ margin: '8px 0 0' }}>Each day of the capture week had its own attacks; Monday is attack-free.</p>
          </div>
          <div className="card">
            <div className="card-head"><h3>Attack flows by category</h3><span className="faint small">{num(malicious)} malicious flows</span></div>
            <BarList items={catItems} color={SERIES[1]} />
          </div>
        </div>
      )}
    </div>
  )
}
