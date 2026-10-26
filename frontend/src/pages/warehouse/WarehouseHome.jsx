import { NavLink, Route, Routes } from 'react-router-dom'
import { api } from '../../api'
import { useAuth } from '../../auth'
import { ErrorBox, useApi } from '../../components/ui'
import { EtlButtons } from './Etl'
import Olap from './Olap'
import Overview from './Overview'
import Schemas from './Schemas'

export default function WarehouseHome() {
  const { user } = useAuth()
  const ov = useApi(() => api('/dw/overview'), [], 3000)
  const built = ov.data?.built
  const running = ov.data?.etl?.running
  return (
    <div className="container page">
      <div className="row between" style={{ marginBottom: 18, alignItems: 'flex-end' }}>
        <div>
          <h2 style={{ margin: 0 }}>Data warehouse</h2>
          <p className="muted" style={{ margin: 0 }}>
            A separate analysis copy of the project's data: dimensional schemas, ETL and OLAP (DWM Module 1).
            It never feeds the detection model.
          </p>
        </div>
      </div>
      <ErrorBox error={ov.error} />
      <nav className="tabs">
        <NavLink end to="/warehouse">Overview</NavLink>
        <NavLink to="/warehouse/schemas">Schemas</NavLink>
        <NavLink to="/warehouse/olap">OLAP cube</NavLink>
      </nav>
      {ov.data && !built && (
        <div className="card empty" style={{ marginBottom: 20 }}>
          <h3>The warehouse has not been built yet</h3>
          <p className="muted">
            {user?.role === 'admin'
              ? 'Run a full ETL load once (about a minute). It reads the cleaned dataset, the raw timestamps and the portal database.'
              : 'Ask an administrator to run the ETL job once.'}
          </p>
          {user?.role === 'admin' && <EtlButtons state={ov.data.etl} onStart={ov.reload} built={false} />}
          {running && <p className="muted small" style={{ marginTop: 10 }}>Building… this takes about half a minute.</p>}
        </div>
      )}
      <Routes>
        <Route index element={<Overview data={ov.data} />} />
        <Route path="schemas" element={<Schemas built={built} />} />
        <Route path="olap" element={<Olap built={built} />} />
      </Routes>
    </div>
  )
}
