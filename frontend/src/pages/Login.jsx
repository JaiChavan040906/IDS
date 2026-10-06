import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

const DEMO = [
  ['analyst', 'analyst123', 'Security Analyst'],
  ['admin', 'admin123', 'Administrator'],
]

export default function Login() {
  const { user, login } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={user.role === 'admin' ? '/admin' : '/analyst'} replace />

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const u = await login(username, password)
      nav(loc.state?.from || (u.role === 'admin' ? '/admin' : '/analyst'), { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card glow stack" onSubmit={submit}>
        <div>
          <h2>Sign in</h2>
          <p className="muted" style={{ margin: 0 }}>Analyst and administrator console</p>
        </div>
        <label className="field">Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required />
        </label>
        <label className="field">Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {error && <div className="error">{error}</div>}
        <button className="btn primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <div>
          <p className="faint small" style={{ margin: '4px 0 0' }}>Demo accounts (simulated login): click to fill</p>
          <div className="demo-accounts">
            {DEMO.map(([u, p, r]) => (
              <button type="button" key={u} onClick={() => { setUsername(u); setPassword(p) }}>
                <b className="mono">{u}</b> / <span className="mono">{p}</span> · {r}
              </button>
            ))}
          </div>
        </div>
      </form>
    </div>
  )
}
