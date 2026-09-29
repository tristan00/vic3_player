import { DataGrid } from '@/components/DataGrid'
import { Section, Tabs, useTab } from '@/components/primitives'
import { policyLink } from '@/routes/PolicyRun'

const VIEWS = ['runs', 'initializer', 'picker', 'outcomes']
const LABELS = { runs: 'Overview', initializer: 'Action weights', picker: 'Block selection', outcomes: 'Objectives & outcomes' }
const INITIALIZER = ['weights', 'proposals', 'candidates', 'importance', 'observations']
const PICKER = ['decisions', 'action_offers', 'model', 'importance']
const TABLES: Record<string, string> = { proposals: 'smac_proposal', candidates: 'smac_candidate', importance: 'smac_importance', observations: 'smac_observation' }

export function Policy() {
  const view = useTab(VIEWS)
  const overview = useTab(['runs', 'configurations'], 'overview')
  const initializer = useTab(INITIALIZER, 'initializer_view')
  const picker = useTab(PICKER, 'picker_view')
  return (
    <div className="space-y-5">
      <h1 className="font-semibold">Policy</h1>
      <p className="text-dim text-sm">Action weights shape the proposed blocks. The block picker selects what to execute. Objectives define how results are scored.</p>
      <Tabs views={VIEWS} labels={LABELS} />
      {view === 'runs' && <Section title="Policy across runs">
        <Tabs views={['runs', 'configurations']} param="overview" />
        {overview === 'runs'
          ? <DataGrid id="runs" url="/api/policy/runs" columns={['run', 'state', 'initializer', 'picker', 'years', 'reward']} link={policyLink} live />
          : <><p className="text-dim mb-3 text-sm">Averages use scored runs only, with equal weight per run. Gains compare the starting value with the peak in the final game year, matching run rewards. Gain/year divides each run’s percentage gain by its elapsed game years before averaging; it is not compounded growth and excludes zero-duration runs. Average reward uses each run’s own objective weights; raw gains help compare setups with different objectives. Unscored runs are excluded, not counted as zero.</p><DataGrid id="configs" url="/api/policy/configs" link={policyLink} live /></>}
      </Section>}
      {view === 'initializer' && <Section title="Action weights">
        <p className="text-dim mb-3 text-sm">Each run starts with an action weight vector from the random or SMAC initializer. These weights control action sampling while blocks are generated; they are separate from the objective weights.</p>
        <Tabs views={INITIALIZER} param="initializer_view" labels={{ weights: 'All run weights', proposals: 'SMAC proposals', candidates: 'SMAC alternatives', importance: 'SMAC importance', observations: 'SMAC observations' }} />
        {initializer === 'weights'
          ? <DataGrid id="weights" url="/api/policy/weights" link={(col, cell) => col.kind === 'run' && cell.ref ? `/policy/runs/${cell.ref.id}?view=initializer` : undefined} live />
          : <DataGrid key={initializer} id={TABLES[initializer]} url={`/api/meta/${TABLES[initializer]}`} initial={{ sort: 'run_id', desc: true }} link={(col, cell) => col.kind === 'run' && cell.ref ? `/policy/runs/${cell.ref.id}?view=initializer&initializer_view=${initializer}` : undefined} live />}
      </Section>}
      {view === 'picker' && <Section title="Block selection">
        <p className="text-dim mb-3 text-sm">The picker chooses among generated action blocks at each decision. Open a run to compare its blocks and rankings.</p>
        <Tabs views={PICKER} param="picker_view" labels={{ decisions: 'Decisions by run', action_offers: 'Action offer totals', model: 'CatBoost models', importance: 'CatBoost importance' }} />
        {picker === 'decisions' && <DataGrid id="picker_runs" url="/api/policy/runs" columns={['run', 'state', 'picker', 'candidates']} link={(col, cell) => col.kind === 'run' && cell.ref ? `/policy/runs/${cell.ref.id}?view=picker` : undefined} live />}
        {picker === 'action_offers' && <DataGrid id="offers" url="/api/policy/picker-actions" />}
        {(picker === 'model' || picker === 'importance') && <DataGrid key={picker} id={`pick_${picker}`} url={`/api/meta/pick_${picker}` } initial={{ sort: 'run_id', desc: true }} link={(col, cell) => col.kind === 'run' && cell.ref ? `/policy/runs/${cell.ref.id}?view=picker&picker_view=${picker}` : undefined} live />}
      </Section>}
      {view === 'outcomes' && <Section title="Objectives and measured rewards">
        <p className="text-dim mb-3 text-sm">Objective weights combine GDP, population, and standard of living gains into the reward. Open a run for the full calculation.</p>
        <DataGrid id="outcomes" url="/api/policy/runs" columns={['run', 'state', 'objective_gdp', 'objective_population', 'objective_sol', 'objective_alpha', 'years', 'reward']} link={(col, cell) => col.kind === 'run' && cell.ref ? `/policy/runs/${cell.ref.id}?view=outcomes` : undefined} live />
      </Section>}
    </div>
  )
}
