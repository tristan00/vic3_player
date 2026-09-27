import { DataGrid } from '@/components/DataGrid'
import { Section } from '@/components/primitives'
import { policyLink } from '@/routes/PolicyRun'

const META = ['smac_proposal', 'smac_candidate', 'smac_importance', 'smac_observation', 'pick_model', 'pick_candidate', 'pick_candidate_action']

export function Policy() {
  return (
    <div className="space-y-5">
      <Section title="runs">
        <DataGrid id="runs" url="/api/policy/runs" link={policyLink} live />
      </Section>
      <Section title="configurations">
        <DataGrid id="configs" url="/api/policy/configs" link={policyLink} live />
      </Section>
      <Section title="picker offers by action">
        <DataGrid id="offers" url="/api/policy/picker-actions" />
      </Section>
      {META.map((t) => (
        <Section key={t} title={<span className="num">{t}</span>}>
          <DataGrid id={t} url={`/api/meta/${t}`} initial={{ sort: 'run_id', desc: true }} link={policyLink} live />
        </Section>
      ))}
    </div>
  )
}
