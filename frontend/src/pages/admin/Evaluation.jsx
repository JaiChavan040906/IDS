import { api, num, pct } from '../../api'
import { ErrorBox, Stat, useApi } from '../../components/ui'

export default function Evaluation() {
  const { data, error } = useApi(() => api('/admin/evaluation'), [], 5000)
  const av = data?.analyst_vs_truth
  return (
    <div className="stack">
      <div className="note">{data?.note || 'Uses hidden ground-truth labels. For evaluation only; never shown to analysts.'}</div>
      <ErrorBox error={error} />
      <div className="grid g3">
        <Stat label="Analyst accuracy vs truth" value={pct(av?.analyst_accuracy, 1)} sub={`${num(av?.decisive_feedback)} decisive decisions`} />
        <Stat label="Model accuracy on the same alerts" value={pct(av?.model_accuracy_on_same_alerts, 1)} sub="where analysts decided" />
        <Stat label="Model accuracy in review queue" value={pct(data?.review_queue_model_accuracy, 1)} sub={`${num(data?.review_queue_size)} referred flows: low is expected`} />
      </div>
      <div className="card pad-0"><div className="table-wrap">
        <table>
          <thead><tr><th>Model version</th><th className="right">Flows scored</th><th className="right">Accuracy</th><th className="right">Referral rate</th><th className="right">Missed attacks (auto-closed)</th></tr></thead>
          <tbody>
            {data?.live_by_model_version.map((r) => (
              <tr key={r.version}><td className="mono">{r.version}</td><td className="right">{num(r.flows)}</td>
                <td className="right mono">{pct(r.accuracy, 2)}</td><td className="right mono">{pct(r.referral_rate, 2)}</td><td className="right">{num(r.missed_attacks)}</td></tr>
            ))}
            {data && !data.live_by_model_version.length && <tr><td colSpan={5} className="muted">No traffic replayed yet.</td></tr>}
          </tbody>
        </table>
      </div></div>
    </div>
  )
}
