import { useState } from 'react'
import { api } from '../../api'
import { ErrorBox, useApi } from '../../components/ui'
import SchemaDiagram from './SchemaDiagram'
import { Comparison, SampleTable } from './shared'

const SCHEMAS = {
  star: {
    label: 'Star schema',
    text: 'One fact table in the centre; every dimension joins to it directly. Dimensions are denormalised (dim_attack stores category and benign/malicious next to the class), so any question needs at most one join per dimension.',
    width: 1000, height: 640,
    layout: { fact_flow: [500, 300], dim_time: [150, 160], dim_attack: [850, 130],
      dim_service: [850, 430], dim_protocol: [150, 470], dim_split: [500, 575] },
  },
  snowflake: {
    label: 'Snowflake schema',
    text: 'The same facts, but dimensions are normalised into sub-dimensions: category moves out of the attack dimension into dim_category, and the date moves out of the time dimension into dim_date. Less repetition, more joins.',
    width: 1300, height: 680,
    layout: { fact_flow: [650, 320], dim_time_sf: [330, 130], dim_date: [110, 330],
      dim_attack_sf: [970, 130], dim_category: [1190, 330], dim_service: [970, 520],
      dim_protocol: [330, 540], dim_split: [650, 610] },
  },
  constellation: {
    label: 'Fact constellation',
    text: 'Two fact tables share dimensions (conformed dimensions): fact_alert (what the model raised) and fact_review (what the analyst decided) both use dim_time, dim_attack and dim_model. fact_review has no measures: it is a factless fact table.',
    width: 1300, height: 680,
    layout: { fact_alert: [380, 340], fact_review: [920, 340], dim_time: [650, 115],
      dim_attack: [650, 360], dim_model: [650, 580], dim_route: [110, 130], dim_service: [110, 360],
      dim_protocol: [110, 570], dim_analyst: [1190, 200], dim_verdict: [1190, 480] },
  },
}

export default function Schemas({ built }) {
  const [which, setWhich] = useState('star')
  const [selected, setSelected] = useState('fact_flow')
  const { data, error } = useApi(() => (built ? api('/dw/tables') : Promise.resolve(null)), [built])
  const s = SCHEMAS[which]
  return (
    <div className="stack">
      <div className="row between">
        <div className="seg">
          {Object.entries(SCHEMAS).map(([k, v]) => (
            <button key={k} className={which === k ? 'on' : ''} onClick={() => setWhich(k)}>{v.label}</button>
          ))}
        </div>
        <span className="faint small">Click a table to see its rows. 🔑 primary key · → foreign key</span>
      </div>
      <ErrorBox error={error} />
      <div className="card">
        <h3 style={{ marginBottom: 6 }}>{s.label}</h3>
        <p className="muted" style={{ marginBottom: 12 }}>{s.text}</p>
        {data && <SchemaDiagram tables={data} layout={s.layout} width={s.width} height={s.height}
          selected={selected} onSelect={setSelected} />}
      </div>
      {built && selected && <SampleTable name={selected} />}
      {built && which === 'snowflake' && <Comparison which="snowflake" />}
    </div>
  )
}
