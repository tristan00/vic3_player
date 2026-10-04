import { DataGrid } from '@/components/DataGrid'
import { Section, Tabs, useTab } from '@/components/primitives'
import { Initializers, policyLink } from '@/routes/PolicyRun'
import { PICKERS } from '@/components/Pickers'
import { RewardFormula } from '@/components/Reward'

const VIEWS = ['runs', 'initializer', 'picker', 'outcomes']
const LABELS = { runs: 'Overview', initializer: 'Action weights', picker: 'Block selection', outcomes: 'Rewards & outcomes' }
const INITIALIZER = ['initializers', 'catalogue', 'weights', 'proposals', 'candidates', 'importance', 'observations', 'svr_proposals', 'svr_coefficients', 'svr_observations']
const INITIALIZER_LABELS = { initializers: 'Initializers', catalogue: 'Advisor actions', weights: 'All run weights', proposals: 'SMAC proposals', candidates: 'SMAC alternatives', importance: 'SMAC importance',
  observations: 'SMAC observations', svr_proposals: 'SVR proposals', svr_coefficients: 'SVR effects', svr_observations: 'SVR observations' }
const PICKER = ['decisions', 'action_offers', 'model', 'importance']
const TABLES: Record<string, string> = { proposals: 'smac_proposal', candidates: 'smac_candidate', importance: 'smac_importance', observations: 'smac_observation',
  svr_proposals: 'svr_proposal', svr_coefficients: 'svr_coefficient', svr_observations: 'svr_observation' }

export function Policy() {
  const view = useTab(VIEWS)
  const overview = useTab(['runs', 'configurations'], 'overview')
  const initializer = useTab(INITIALIZER, 'initializer_view')
  const pickerType = useTab(['all', ...Object.keys(PICKERS)], 'picker_type')
  const pickerViews = pickerType === 'first' ? ['decisions'] : PICKER
  const picker = useTab(pickerViews, 'picker_view')
  const pickerFilter = pickerType === 'all' ? [] : [`picker:${pickerType}`]
  return (
    <div className="space-y-5">
      <h1 className="font-semibold">Policy</h1>
      <p className="text-dim text-sm">Action weights shape the proposed blocks. The block picker selects what to execute. The learned initializers and both CatBoost pickers use building stock, population and GDP to score outcomes.</p>
      <Tabs views={VIEWS} labels={LABELS} />
      {view === 'runs' && <Section title="Policy across runs">
        <Tabs views={['runs', 'configurations']} param="overview" />
        {overview === 'runs'
          ? <DataGrid id="runs.endgame" url="/api/policy/runs" columns={['run', 'state', 'initializer', 'picker', 'years', 'stock.contribution', 'population.contribution', 'gdp.contribution', 'reward']} link={policyLink} live />
          : <DataGrid id="configs.endgame" url="/api/policy/configs" link={policyLink} live />}
        <p className="text-dim mt-3 text-xs">Completed runs are recalculated with the current fixed reward. Configuration comparisons use the median run score.</p>
      </Section>}
      {view === 'initializer' && <Section title="Action weights">
        <p className="text-dim mb-3 text-sm">Each run starts with action sampling weights from the random, SMAC or SVR initializer. SMAC and SVR learn from rank-normalized three-metric rewards measured from each run’s opening snapshot.</p>
        <Tabs views={INITIALIZER} param="initializer_view" labels={INITIALIZER_LABELS} />
        {initializer === 'initializers' && <Initializers />}
        {initializer === 'catalogue' && <DataGrid id="catalogue" url="/api/policy/catalogue" live />}
        {initializer === 'weights'
          ? <DataGrid id="weights" url="/api/policy/weights" link={(col, cell) => col.kind === 'run' && cell.ref ? `/policy/runs/${cell.ref.id}?view=initializer` : undefined} live />
          : initializer !== 'initializers' && initializer !== 'catalogue' && <DataGrid key={initializer} id={TABLES[initializer]} url={`/api/meta/${TABLES[initializer]}`} initial={{ sort: 'run_id', desc: true }} link={(col, cell) => col.kind === 'run' && cell.ref ? `/policy/runs/${cell.ref.id}?view=initializer&initializer_view=${initializer}` : undefined} live />}
      </Section>}
      {view === 'picker' && <Section title="Block selection">
        <Tabs views={['all', ...Object.keys(PICKERS)]} param="picker_type" labels={{ all: 'All pickers', ...Object.fromEntries(Object.entries(PICKERS).map(([name, p]) => [name, p.title])) }} />
        <Tabs views={pickerViews} param="picker_view" labels={{ decisions: 'Runs & decisions', action_offers: 'Action offer totals', model: 'Recorded models', importance: 'Feature importance' }} />
        {picker === 'decisions' && <DataGrid key={pickerType} id={`picker_runs.${pickerType}`} url="/api/policy/runs" fixed={pickerFilter} columns={['run', 'state', 'picker', 'candidates']} link={(col, cell) => col.kind === 'run' && cell.ref ? `/policy/runs/${cell.ref.id}?view=picker` : undefined} live />}
        {picker === 'action_offers' && <><p className="text-dim mb-3 text-sm">Recorded scored candidates, separated by picker. Shares are calculated within each picker. First-block runs do not record scored alternatives; open a run to inspect its executed blocks.</p><DataGrid key={pickerType} id={`offers.${pickerType}`} url="/api/policy/picker-actions" fixed={pickerFilter} live /></>}
        {(picker === 'model' || picker === 'importance') && <><p className="text-dim mb-3 text-sm">These are the models recorded when each run began. Whole-block and piecewise models use different features and score calculations. First-block selection has no fitted model.</p><DataGrid key={`${picker}.${pickerType}`} id={`pick_${picker}.${pickerType}`} url={`/api/meta/pick_${picker}` } fixed={pickerFilter} initial={{ sort: 'run_id', desc: true }} link={(col, cell) => col.kind === 'run' && cell.ref ? `/policy/runs/${cell.ref.id}?view=picker&picker_view=${picker}` : undefined} live /></>}
      </Section>}
      {view === 'outcomes' && <Section title="Three-metric reward">
        <RewardFormula />
        <p className="text-dim my-3 text-xs">These run scores are recalculated with the current formula. Open a run for its component breakdown.</p>
        <DataGrid id="outcomes.endgame" url="/api/policy/runs" columns={['run', 'state', 'years', 'stock.end_ratio', 'population.end_ratio', 'gdp.end_ratio', 'stock.contribution', 'population.contribution', 'gdp.contribution', 'reward']} link={(col, cell) => col.kind === 'run' && cell.ref ? `/policy/runs/${cell.ref.id}?view=outcomes` : undefined} live />
      </Section>}
    </div>
  )
}
