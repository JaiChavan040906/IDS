import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, RequireRole } from './auth'
import Layout from './components/Layout'
import { FeaturesProvider, useFeatures } from './features'
import About from './pages/About'
import Login from './pages/Login'
import AnalystHome from './pages/analyst/AnalystHome'
import AdminHome from './pages/admin/AdminHome'
import WarehouseHome from './pages/warehouse/WarehouseHome'
import './styles.css'

// The Warehouse tab exists only when the server runs with the warehouse switched on.
function WarehouseGate() {
  const { loaded, warehouse } = useFeatures()
  if (!loaded) return null
  if (!warehouse) return <Navigate to="/about" replace />
  return <RequireRole roles={['analyst', 'admin']}><WarehouseHome /></RequireRole>
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <FeaturesProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Navigate to="/about" replace />} />
              <Route path="/about" element={<About />} />
              <Route path="/login" element={<Login />} />
              <Route path="/analyst/*" element={
                <RequireRole roles={['analyst', 'admin']}><AnalystHome /></RequireRole>} />
              <Route path="/warehouse/*" element={<WarehouseGate />} />
              <Route path="/admin/*" element={
                <RequireRole roles={['admin']}><AdminHome /></RequireRole>} />
              <Route path="*" element={<Navigate to="/about" replace />} />
            </Route>
          </Routes>
        </FeaturesProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
