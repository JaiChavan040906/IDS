// Draws a dimensional schema as boxes (tables) and lines (foreign keys), from the live
// warehouse metadata. Positions are fixed per schema; columns and row counts are real.
const W = 210
const HEAD = 40
const LINE = 15
const MAX_COLS = 9

const COLORS = {
  fact: 'var(--accent)', 'factless fact': 'var(--accent)', dimension: 'var(--blue)',
  'snowflake dimension': 'var(--blue)', 'snowflake sub-dimension': 'var(--amber)',
}

function boxHeight(t) {
  const n = Math.min(t.columns.length, MAX_COLS) + (t.columns.length > MAX_COLS ? 1 : 0)
  return HEAD + n * LINE + 10
}

export default function SchemaDiagram({ tables, layout, width, height, selected, onSelect }) {
  const byName = Object.fromEntries(tables.map((t) => [t.name, t]))
  const shown = Object.keys(layout).filter((n) => byName[n])
  const links = []
  shown.forEach((n) => byName[n].foreign_keys.forEach((fk) => {
    if (layout[fk.table] && byName[fk.table]) links.push([n, fk.table, fk.column])
  }))
  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', display: 'block' }}
      role="img" aria-label="Schema diagram">
      {links.map(([a, b, col]) => {
        const [x1, y1] = layout[a]
        const [x2, y2] = layout[b]
        return (
          <g key={`${a}-${b}-${col}`}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--border-2)" strokeWidth="1.5" />
          </g>
        )
      })}
      {shown.map((n) => {
        const t = byName[n]
        const [cx, cy] = layout[n]
        const h = boxHeight(t)
        const x = cx - W / 2
        const y = cy - h / 2
        const color = COLORS[t.kind] || 'var(--muted)'
        const fkCols = new Set(t.foreign_keys.map((f) => f.column))
        const cols = t.columns.slice(0, MAX_COLS)
        return (
          <g key={n} onClick={() => onSelect?.(n)} style={{ cursor: 'pointer' }}>
            <rect x={x} y={y} width={W} height={h} rx="8" fill="var(--surface)"
              stroke={selected === n ? 'var(--text)' : color} strokeWidth={selected === n ? 2.5 : 1.5} />
            <rect x={x} y={y} width={W} height={HEAD - 6} rx="8" fill={color} opacity="0.16" />
            <text x={x + 10} y={y + 16} fill="var(--text)" fontSize="12.5" fontWeight="700" fontFamily="var(--mono)">{n}</text>
            <text x={x + 10} y={y + 29} fill="var(--muted)" fontSize="10.5">{t.kind} · {t.rows.toLocaleString()} rows</text>
            {cols.map((c, i) => (
              <text key={c.name} x={x + 10} y={y + HEAD + 8 + i * LINE} fontSize="11" fontFamily="var(--mono)"
                fill={c.pk ? 'var(--text)' : fkCols.has(c.name) ? color : 'var(--muted)'}>
                {c.pk ? '🔑 ' : fkCols.has(c.name) ? '→ ' : '   '}{c.name}
              </text>
            ))}
            {t.columns.length > MAX_COLS && (
              <text x={x + 10} y={y + HEAD + 8 + MAX_COLS * LINE} fontSize="11" fill="var(--faint)">
                + {t.columns.length - MAX_COLS} more columns
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
