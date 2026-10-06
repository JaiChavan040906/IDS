import { useState } from 'react'
import { api } from '../../api'
import { useAuth } from '../../auth'
import { Badge, ErrorBox, useApi } from '../../components/ui'

export default function Users() {
  const { user: me } = useAuth()
  const { data, error, reload } = useApi(() => api('/admin/users'))
  const [f, setF] = useState({ username: '', full_name: '', role: 'analyst', password: '' })
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const create = async (e) => {
    e.preventDefault()
    setErr(null)
    try { await api('/admin/users', { method: 'POST', body: f }); setF({ username: '', full_name: '', role: 'analyst', password: '' }); reload() } catch (x) { setErr(x) }
  }
  const patch = async (id, body) => {
    setErr(null)
    try { await api(`/admin/users/${id}`, { method: 'PATCH', body }); reload() } catch (x) { setErr(x) }
  }
  const reset = (u) => {
    const p = window.prompt(`New password for ${u.username} (min 6 characters)`)
    if (p) patch(u.id, { password: p })
  }

  return (
    <div className="grid g3">
      <div className="card pad-0 span2"><div className="table-wrap">
        <ErrorBox error={error || err} />
        <table>
          <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {data?.map((u) => (
              <tr key={u.id}>
                <td><b>{u.full_name}</b><div className="faint mono small">{u.username}</div></td>
                <td>
                  <select value={u.role} disabled={u.id === me.id} onChange={(e) => patch(u.id, { role: e.target.value })} style={{ width: 120 }}>
                    <option value="analyst">analyst</option><option value="admin">admin</option>
                  </select>
                </td>
                <td>{u.active ? <Badge kind="active">active</Badge> : <Badge>disabled</Badge>}</td>
                <td className="row" style={{ gap: 6 }}>
                  <button className="btn sm" disabled={u.id === me.id} onClick={() => patch(u.id, { active: !u.active })}>{u.active ? 'Disable' : 'Enable'}</button>
                  <button className="btn sm ghost" onClick={() => reset(u)}>Reset password</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div></div>
      <form className="card stack" onSubmit={create}>
        <h3 style={{ margin: 0 }}>Add user</h3>
        <label className="field">Full name<input value={f.full_name} onChange={set('full_name')} required /></label>
        <label className="field">Username<input value={f.username} onChange={set('username')} required minLength={3} /></label>
        <label className="field">Role
          <select value={f.role} onChange={set('role')}><option value="analyst">Security Analyst</option><option value="admin">Administrator</option></select>
        </label>
        <label className="field">Initial password<input type="password" value={f.password} onChange={set('password')} required minLength={6} /></label>
        <button className="btn primary">Create user</button>
      </form>
    </div>
  )
}
