import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, RequireRole } from './auth'
import Layout from './components/Layout'
import About from './pages/About'
import Login from './pages/Login'
import AnalystHome from './pages/analyst/AnalystHome'
import AdminHome from './pages/admin/AdminHome'
import './styles.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/about" replace />} />
            <Route path="/about" element={<About />} />
            <Route path="/login" element={<Login />} />
            <Route path="/analyst/*" element={
              <RequireRole roles={['analyst', 'admin']}><AnalystHome /></RequireRole>} />
            <Route path="/admin/*" element={
              <RequireRole roles={['admin']}><AdminHome /></RequireRole>} />
            <Route path="*" element={<Navigate to="/about" replace />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
