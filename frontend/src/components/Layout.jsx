import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { useFeatures } from '../features'

export default function Layout() {
  const { user, logout } = useAuth()
  const { warehouse } = useFeatures()
  const nav = useNavigate()
  return (
    <>
      <header className="nav">
        <div className="container">
          <Link to="/about" className="brand"><span className="dot" /><span className="label">Sentinel IDS</span></Link>
          <nav className="nav-links">
            <NavLink to="/about">ABOUT</NavLink>
            <NavLink to="/analyst">ANALYST</NavLink>
            <NavLink to="/admin">ADMINISTRATION</NavLink>
            {warehouse && <NavLink to="/warehouse">WAREHOUSE</NavLink>}
          </nav>
          <div className="spacer" />
          {user ? (
            <div className="userchip">
              <span className="who"><b>{user.full_name}</b></span>
              <span className={`badge ${user.role}`}>{user.role}</span>
              <button className="btn sm ghost" onClick={async () => { await logout(); nav('/about') }}>Sign out</button>
            </div>
          ) : (
            <Link to="/login" className="btn sm primary">Sign in</Link>
          )}
        </div>
      </header>
      <Outlet />
    </>
  )
}
