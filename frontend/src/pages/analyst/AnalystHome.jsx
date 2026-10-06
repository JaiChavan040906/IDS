import { NavLink, Route, Routes } from 'react-router-dom'
import { api } from '../../api'
import { useApi } from '../../components/ui'
import AlertDetail from './AlertDetail'
import AlertList from './AlertList'
import Dashboard from './Dashboard'
import KnowledgeRepo from './KnowledgeRepo'

export default function AnalystHome() {
  const { data } = useApi(() => api('/stats/overview', { params: { minutes: 1440 } }), [], 10000)
  const reviewOpen = data?.open_queue?.filter((q) => q.decision === 'review').reduce((s, q) => s + q.count, 0)
  const alertOpen = data?.open_queue?.filter((q) => q.decision === 'auto_alert').reduce((s, q) => s + q.count, 0)
  return (
    <div className="container page">
      <div className="row between" style={{ marginBottom: 18 }}>
        <div>
          <h2 style={{ margin: 0 }}>Analyst console</h2>
          <p className="muted" style={{ margin: 0 }}>Review uncertain flows, record decisions, search past incidents.</p>
        </div>
      </div>
      <nav className="tabs">
        <NavLink end to="/analyst">Dashboard</NavLink>
        <NavLink to="/analyst/review">Review queue{reviewOpen !== undefined && <span className="count">{reviewOpen}</span>}</NavLink>
        <NavLink to="/analyst/alerts">Confident alerts{alertOpen !== undefined && <span className="count">{alertOpen}</span>}</NavLink>
        <NavLink to="/analyst/resolved">Resolved</NavLink>
        <NavLink to="/analyst/kr">Knowledge Repository</NavLink>
      </nav>
      <Routes>
        <Route index element={<Dashboard />} />
        <Route path="review" element={<AlertList key="review" decision="review" status="open"
          intro="Flows the model was not sure about. Your decision here trains future models (after admin verification)." />} />
        <Route path="alerts" element={<AlertList key="alerts" decision="auto_alert" status="open"
          intro="Flows the model flagged as attacks with high confidence. Spot-check them; mark false positives." />} />
        <Route path="resolved" element={<AlertList key="resolved" status="resolved" intro="Alerts with a recorded decision." />} />
        <Route path="alerts/:id" element={<AlertDetail />} />
        <Route path="kr/*" element={<KnowledgeRepo />} />
      </Routes>
    </div>
  )
}
