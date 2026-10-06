import { useState } from 'react'
import { api, time } from '../../api'
import { Badge, ErrorBox, useApi } from '../../components/ui'

const GROUPS = ['', 'auth', 'alert', 'feedback', 'model', 'retrain', 'replay', 'user']

export default function Audit() {
  const [action, setAction] = useState('')
  const { data, error } = useApi(() => api('/admin/audit', { params: { action, limit: 300 } }), [action], 5000)
  return (
    <div className="stack">
      <div className="seg" style={{ alignSelf: 'flex-start', flexWrap: 'wrap' }}>
        {GROUPS.map((g) => <button key={g || 'all'} className={action === g ? 'on' : ''} onClick={() => setAction(g)}>{g || 'all'}</button>)}
      </div>
      <ErrorBox error={error} />
      <div className="card pad-0"><div className="table-wrap">
        <table>
          <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
          <tbody>
            {data?.map((a) => (
              <tr key={a.id}>
                <td className="small faint nowrap">{time(a.ts)}</td>
                <td>{a.username}</td>
                <td><Badge kind={a.action.startsWith('model') ? 'approved' : ''}>{a.action}</Badge></td>
                <td className="mono small">{a.target}</td>
                <td className="mono small faint" style={{ maxWidth: 460, overflowWrap: 'anywhere' }}>{Object.keys(a.details || {}).length ? JSON.stringify(a.details) : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div></div>
    </div>
  )
}
