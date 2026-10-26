// A real OLAP cube, drawn in isometric 3-D: X = column dimension, Y = row dimension,
// Z = depth dimension. Every small block is one cell (one member of each of the three
// dimensions); its colour shows the measure. A slice or dice lights up its part of the cube.
import { useMemo, useState } from 'react'

const S = 38                                 // block size (px)
const GAP = 0.12                             // space between blocks (fraction of a block)
const LOW = [0x18, 0x4f, 0x95]               // sequential blue ramp, dark -> light (step 600 -> 250)
const HIGH = [0x86, 0xb6, 0xef]

const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t))
const rgb = (c) => `rgb(${c[0]},${c[1]},${c[2]})`
const shade = (c, f) => c.map((v) => Math.max(0, Math.min(255, Math.round(v * f))))
const short = (s) => {
  const t = String(s).replace(/ 20\d\d/, '')
  return t.length > 15 ? `${t.slice(0, 14)}…` : t
}

export default function Cube3D({ cube, fmt }) {
  const [hover, setHover] = useState(null)
  const model = useMemo(() => {
    if (!cube) return null
    const [ax, ay, az] = cube.axes
    const nx = ax.members.length, ny = ay.members.length, nz = az.members.length
    const P = (i, k, j) => [(i - k) * S * 0.866, (i + k) * S * 0.5 + j * S]
    const values = new Map(cube.cells.map(([i, j, k, v]) => [`${i},${j},${k}`, v]))
    const max = Math.max(1e-9, ...cube.cells.map((c) => Math.abs(c[3] || 0)))
    const hl = cube.highlight || {}
    const inside = (i, j, k) => [[0, ax, i], [1, ay, j], [2, az, k]].every(([n, a, idx]) =>
      !hl[n] || hl[n].includes(a.members[idx]))
    const hasHl = Object.keys(hl).length > 0
    const blocks = []
    for (let i = 0; i < nx; i++) for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) {
      const v = values.get(`${i},${j},${k}`)
      blocks.push({ i, j, k, v, on: !hasHl || inside(i, j, k) })
    }
    blocks.sort((a, b) => (a.i + a.k) - (b.i + b.k) || b.j - a.j)    // far first, lower first
    const pts = [P(0, 0, 0), P(nx, 0, 0), P(0, nz, 0), P(nx, nz, ny), P(0, nz, ny), P(nx, 0, ny)]
    const minX = Math.min(...pts.map((p) => p[0])) - 190, maxX = Math.max(...pts.map((p) => p[0])) + 190
    const minY = Math.min(...pts.map((p) => p[1])) - 34, maxY = Math.max(...pts.map((p) => p[1])) + 80
    return { ax, ay, az, nx, ny, nz, P, blocks, max, hasHl, box: [minX, minY, maxX - minX, maxY - minY] }
  }, [cube])

  if (!model) return null
  const { ax, ay, az, nx, ny, nz, P, blocks, max, hasHl, box } = model
  const poly = (ps) => ps.map((p) => p.join(',')).join(' ')

  const face = (b) => {
    const e = GAP, i0 = b.i + e, i1 = b.i + 1 - e, k0 = b.k + e, k1 = b.k + 1 - e, j0 = b.j + e, j1 = b.j + 1 - e
    const top = [P(i0, k0, j0), P(i1, k0, j0), P(i1, k1, j0), P(i0, k1, j0)]
    const left = [P(i0, k1, j0), P(i1, k1, j0), P(i1, k1, j1), P(i0, k1, j1)]
    const right = [P(i1, k0, j0), P(i1, k1, j0), P(i1, k1, j1), P(i1, k0, j1)]
    return { top, left, right }
  }

  return (
    <div>
      <svg className="cube-svg" viewBox={box.join(' ')} style={{ width: '100%', height: 'auto', maxHeight: 560, display: 'block' }}
        role="img" aria-label={`OLAP cube: ${ax.dim_label} by ${ay.dim_label} by ${az.dim_label}`}>
        {blocks.map((b) => {
          const f = face(b)
          const key = `${b.i}-${b.j}-${b.k}`
          if (b.v === undefined || b.v === null) {
            return <polygon key={key} points={poly(f.top)} fill="none" stroke="#1d2733" strokeWidth="1" />
          }
          const t = Math.log1p(Math.abs(b.v)) / Math.log1p(max)
          const base = mix(LOW, HIGH, t)
          const ghost = hasHl && !b.on
          const op = ghost ? 0.14 : 1
          const isHover = hover && hover.i === b.i && hover.j === b.j && hover.k === b.k
          return (
            <g key={key} opacity={op} onMouseEnter={() => setHover(b)} onMouseLeave={() => setHover(null)} style={{ cursor: 'default' }}>
              <polygon points={poly(f.left)} fill={rgb(shade(base, 0.82))} />
              <polygon points={poly(f.right)} fill={rgb(shade(base, 0.62))} />
              <polygon points={poly(f.top)} fill={rgb(shade(base, 1.12))}
                stroke={isHover ? '#e7edf4' : hasHl && b.on ? '#ffb547' : 'none'} strokeWidth={isHover || (hasHl && b.on) ? 1.5 : 0} />
            </g>
          )
        })}
        {/* X axis (columns): bottom-left front edge, labels pushed out down-left */}
        {ax.members.map((m, i) => {
          const [x, y] = P(i + 0.5, nz, ny)
          return <text key={`x${i}`} x={x - 10} y={y + 14} fontSize="11" fill="#8a97a8" textAnchor="end"><title>{m}</title>{short(m)}</text>
        })}
        {/* Z axis (depth): bottom-right front edge, labels pushed out down-right */}
        {az.members.map((m, k) => {
          const [x, y] = P(nx, k + 0.5, ny)
          return <text key={`z${k}`} x={x + 10} y={y + 14} fontSize="11" fill="#8a97a8"><title>{m}</title>{short(m)}</text>
        })}
        {/* Y axis (rows): left vertical edge */}
        {ay.members.map((m, j) => {
          const [x, y] = P(0, nz, j + 0.5)
          return <text key={`y${j}`} x={x - 12} y={y + 4} fontSize="11" fill="#8a97a8" textAnchor="end"><title>{m}</title>{short(m)}</text>
        })}
        {(() => {
          const [xl, yl] = P(0, nz, ny)          // bottom-left corner
          const [xf, yf] = P(nx, nz, ny)         // bottom-front corner
          const [xr, yr] = P(nx, 0, ny)          // bottom-right corner
          const [xt, yt] = P(0, nz, 0)           // top of the left vertical edge
          return (
            <>
              <text x={(xl + xf) / 2 - 60} y={(yl + yf) / 2 + 58} fontSize="12" fill="#e7edf4" fontWeight="600" textAnchor="end">X: {ax.dim_label} ({ax.level_label}) ↘</text>
              <text x={(xf + xr) / 2 + 60} y={(yf + yr) / 2 + 58} fontSize="12" fill="#e7edf4" fontWeight="600">↙ Z: {az.dim_label} ({az.level_label})</text>
              <text x={xt - 12} y={yt - 14} fontSize="12" fill="#e7edf4" fontWeight="600" textAnchor="end">Y: {ay.dim_label} ({ay.level_label}) ↓</text>
            </>
          )
        })()}
      </svg>
      <div className="row between small" style={{ marginTop: 6, minHeight: 20 }}>
        <span className="muted">
          {hover
            ? <>{ax.dim_label} <b>{hover && ax.members[hover.i]}</b> · {ay.dim_label} <b>{ay.members[hover.j]}</b> · {az.dim_label} <b>{az.members[hover.k]}</b> → <b style={{ color: 'var(--text)' }}>{fmt(hover.v)}</b> {cube.measure.toLowerCase()}</>
            : 'Hover a block to read its cell. Brighter = larger value (log scale). Outlined squares = empty cells.'}
        </span>
        <span className="row" style={{ gap: 6 }}>
          <span className="faint">low</span>
          <span style={{ width: 80, height: 8, borderRadius: 4, background: `linear-gradient(90deg, ${rgb(LOW)}, ${rgb(HIGH)})` }} />
          <span className="faint">high</span>
        </span>
      </div>
    </div>
  )
}
