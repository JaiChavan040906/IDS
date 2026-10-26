import { api, num, pct } from '../../api'
import { Badge, ErrorBox, Stat, useApi } from '../../components/ui'
import { BarList, SERIES, useVisual } from '../../components/charts'

export default function Evaluation() {
  const { data, error } = useApi(() => api('/admin/evaluation'), [], 5000)
  const av = data?.analyst_vs_truth
  const visual = useVisual()
  const lab = (r) => `${r.source_name} · ${r.version}`
  const scored = (data?.live || []).filter((r) => r.attacks)
  return (
    <div className="stack">
      <div className="note">{data?.note || 'Uses hidden ground-truth labels. For evaluation only; never shown to analysts.'}</div>
      <ErrorBox error={error} />
      <div className="grid g3">
        <Stat label="Analyst accuracy vs truth" value={pct(av?.analyst_accuracy, 1)} sub={`${num(av?.decisive_feedback)} decisive decisions`} />
        <Stat label="Model accuracy on the same alerts" value={pct(av?.model_accuracy_on_same_alerts, 1)} sub="where analysts decided" />
        <Stat label="Model accuracy in review queue" value={pct(data?.review_queue_model_accuracy, 1)} sub={`${num(data?.review_queue_size)} referred flows: low is expected`} />
      </div>
      <div className="card pad-0">
        <div className="card-head" style={{ padding: '16px 16px 0' }}>
          <h3>Live results by traffic source and model</h3>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr>
              <th>Traffic source</th><th>Model</th><th className="right">Flows</th><th className="right">Sent to review</th>
              <th className="right">Attacks caught</th><th className="right">Attacks missed</th><th className="right">False alarm rate</th><th className="right">Exact-class accuracy</th>
            </tr></thead>
            <tbody>
              {data?.live.map((r) => (
                <tr key={`${r.source}-${r.version}`}>
                  <td>{r.source_name}{r.labelled_flows === 0 && <div><Badge>no labels</Badge></div>}</td>
                  <td className="mono">{r.version}</td>
                  <td className="right">{num(r.flows)}</td>
                  <td className="right mono">{pct(r.referral_rate, 2)}</td>
                  <td className="right mono">{pct(r.detection_rate, 2)}<div className="faint small">of {num(r.attacks)}</div></td>
                  <td className="right">{num(r.missed_attacks)}</td>
                  <td className="right mono">{pct(r.false_alarm_rate, 3)}</td>
                  <td className="right mono">{pct(r.accuracy, 2)}</td>
                </tr>
              ))}
              {data && !data.live.length && <tr><td colSpan={8} className="muted">No traffic replayed yet.</td></tr>}
            </tbody>
          </table>
        </div>
        <p className="faint small" style={{ padding: '0 16px 16px', margin: 0 }}>
          <b>Attacks caught</b> = true attacks that were alerted or sent to review. <b>Missed</b> = true attacks closed as normal.
          <b> Exact-class accuracy</b> only counts classes our model knows, so it drops on data with new attack types.
          Rows recorded before this view existed show no attack counts.
        </p>
      </div>
      {visual && scored.length > 0 && (
        <div className="grid g2">
          <div className="card">
            <BarList title="Attacks caught (alerted or sent to review), %" color={SERIES[0]} max={1}
              items={scored.map((r) => ({ label: lab(r), value: r.detection_rate }))} format={(v) => pct(v, 2)} />
          </div>
          <div className="card">
            <BarList title="Flows sent to the analyst (referral rate), %" color={SERIES[2]}
              items={scored.map((r) => ({ label: lab(r), value: r.referral_rate }))} format={(v) => pct(v, 2)} />
          </div>
        </div>
      )}
    </div>
  )
}
