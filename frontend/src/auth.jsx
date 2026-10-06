import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api, getToken, setToken } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!getToken()) { setReady(true); return }
    api('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setReady(true))
  }, [])

  useEffect(() => {
    const onLogout = () => setUser(null)
    window.addEventListener('ids-logout', onLogout)
    return () => window.removeEventListener('ids-logout', onLogout)
  }, [])

  const login = useCallback(async (username, password) => {
    const r = await api('/auth/login', { method: 'POST', body: { username, password } })
    setToken(r.token)
    setUser(r.user)
    return r.user
  }, [])

  const logout = useCallback(async () => {
    try { await api('/auth/logout', { method: 'POST' }) } catch { /* already gone */ }
    setToken(null)
    setUser(null)
  }, [])

  return <AuthContext.Provider value={{ user, ready, login, logout }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)

// Wrap a page: only render it for logged-in users with one of `roles`.
export function RequireRole({ roles, children }) {
  const { user, ready } = useAuth()
  const loc = useLocation()
  if (!ready) return <div className="page-loading">Loading…</div>
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />
  if (!roles.includes(user.role)) {
    return (
      <div className="container narrow">
        <div className="card empty">
          <h2>Not available for your role</h2>
          <p className="muted">This area needs the {roles.join(' or ')} role. You are signed in as <b>{user.role}</b>.</p>
        </div>
      </div>
    )
  }
  return children
}
