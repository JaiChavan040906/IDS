// Small chart kit for the "visual" view (shown next to text and tables while the Warehouse
// switch is on). Colours: categorical palette validated for the dark surface #0e141d
// (dataviz validate_palette.js: all checks pass, adjacent CVD ΔE >= 8.4).
import { useState } from 'react'
import { useFeatures } from '../features'

export const SERIES = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767']
export const OTHER = '#5d6a7b'

// Visual extras appear only while the Warehouse switch is on.
export function useVisual() {
  return useFeatures().warehouse
}

const fmt = (v, digits = 2) => (typeof v !== 'number' ? v
  : Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: digits }))

// One 100% bar split into parts, e.g. closed / alert / analyst. Legend + values always shown.
export function SplitBar({ parts, format = (v) => fmt(v), height = 22, title }) {
  const [hover, setHover] = useState(null)
  const total = parts.reduce((s, p) => s + (p.value || 0), 0)
  if (!total) return <p className="faint small" style={{ margin: 0 }}>No data yet.</p>
  return (
    <figure className="viz" style={{ margin: 0 }}>
      {title && <figcaption className="viz-title">{title}</figcaption>}
      <div className="splitbar" style={{ height }} role="img"
        aria-label={parts.map((p) => `${p.label} ${format(p.value)}`).join(', ')}>
        {parts.map((p, i) => p.value > 0 && (
          <span key={p.label} style={{ flexGrow: p.value, background: p.color || SERIES[i], minWidth: 4 }}
            onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
        ))}
      </div>
      <div className="viz-legend">
        {parts.map((p, i) => (
          <span key={p.label} className={hover === i ? 'on' : ''}>
            <i style={{ background: p.color || SERIES[i] }} />{p.label} <b>{format(p.value)}</b>
            <span className="faint"> · {((100 * p.value) / total).toFixed(p.value / total < 0.1 ? 2 : 1)}%</span>
          </span>
        ))}
      </div>
    </figure>
  )
}

// Horizontal bars, one row per item (label left, value right). For magnitudes of one measure.
export function BarList({ items, max, format = (v) => fmt(v), color = SERIES[0], title, signed = false }) {
  const top = max ?? Math.max(1e-9, ...items.map((d) => Math.abs(d.value || 0)))
  return (
    <figure className="viz" style={{ margin: 0 }}>
      {title && <figcaption className="viz-title">{title}</figcaption>}
      <div className="barlist">
        {items.map((d) => {
          const w = Math.min(100, (100 * Math.abs(d.value || 0)) / top)
          const neg = signed && d.value < 0
          return (
            <div key={d.label} className="barlist-row" title={`${d.label}: ${format(d.value)}`}>
              <span className="barlist-label">{d.label}</span>
              <span className="barlist-track">
                <span style={{ width: `${w}%`, background: d.color || (neg ? SERIES[1] : color) }} />
              </span>
              <span className="barlist-value mono">{format(d.value)}</span>
            </div>
          )
        })}
      </div>
    </figure>
  )
}
