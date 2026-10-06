import { NavLink, Route, Routes } from 'react-router-dom'
import Audit from './Audit'
import Evaluation from './Evaluation'
import FeedbackReview from './FeedbackReview'
import Models from './Models'
import Overview from './Overview'
import Retraining from './Retraining'
import Users from './Users'

export default function AdminHome() {
  return (
    <div className="container page">
      <div style={{ marginBottom: 18 }}>
        <h2 style={{ margin: 0 }}>Administration</h2>
        <p className="muted" style={{ margin: 0 }}>System health, traffic replay, model lifecycle, retraining, users and audit.</p>
      </div>
      <nav className="tabs">
        <NavLink end to="/admin">Overview</NavLink>
        <NavLink to="/admin/feedback">Verify feedback</NavLink>
        <NavLink to="/admin/retraining">Retraining</NavLink>
        <NavLink to="/admin/models">Models</NavLink>
        <NavLink to="/admin/evaluation">Evaluation</NavLink>
        <NavLink to="/admin/users">Users</NavLink>
        <NavLink to="/admin/audit">Audit log</NavLink>
      </nav>
      <Routes>
        <Route index element={<Overview />} />
        <Route path="feedback" element={<FeedbackReview />} />
        <Route path="retraining" element={<Retraining />} />
        <Route path="models" element={<Models />} />
        <Route path="evaluation" element={<Evaluation />} />
        <Route path="users" element={<Users />} />
        <Route path="audit" element={<Audit />} />
      </Routes>
    </div>
  )
}
