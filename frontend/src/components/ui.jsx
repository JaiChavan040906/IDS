// Small shared building blocks.
import { useCallback, useEffect, useRef, useState } from 'react'

export function Badge({ kind, children }) {
  return <span className={`badge ${kind || ''}`}>{children ?? kind}</span>
}

export function Stat({ label, value, sub }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

export function Meter({ value, max = 1, threshold, color }) {
  const w = Math.max(0, Math.min(1, value / max)) * 100
  const t = threshold !== undefined ? Math.min(1, threshold / max) * 100 : null
  return (
    <div className={`bar ${color || ''}`}>
      <span style={{ width: `${w}%` }} />
      {t !== null && <i className="mark" style={{ left: `${t}%` }} title="routing threshold" />}
    </div>
  )
}

export function ErrorBox({ error }) {
  return error ? <div className="error">{String(error.message || error)}</div> : null
}

// Load data from the API; optional polling interval in ms.
export function useApi(fn, deps = [], interval = 0) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn
  const load = useCallback(async () => {
    try {
      setData(await fnRef.current())
      setError(null)
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    setLoading(true)
    load()
    if (!interval) return undefined
    const id = setInterval(load, interval)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return { data, error, loading, reload: load, setData }
}

export function Empty({ title, children }) {
  return (
    <div className="card empty">
      <h3>{title}</h3>
      {children && <p className="muted">{children}</p>}
    </div>
  )
}
