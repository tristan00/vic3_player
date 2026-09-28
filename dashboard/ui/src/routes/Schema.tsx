import { DataGrid } from '@/components/DataGrid'
import { Section, Tabs, useTab } from '@/components/primitives'

const VIEWS = ['columns', 'capture_gaps', 'timing']

export function Schema() {
  const view = useTab(VIEWS)
  return (
    <div className="space-y-5">
      <h1 className="font-semibold">Schema</h1>
      <Tabs views={VIEWS} />
      {view === 'columns' && <Section title="recorded columns"><DataGrid id="schema" url="/api/schema" /></Section>}
      {view === 'capture_gaps' && <Section title="capture gaps"><DataGrid id="gaps" url="/api/meta/capture_gap" /></Section>}
      {view === 'timing' && <Section title="dashboard timing"><DataGrid id="timing" url="/api/timing" initial={{ sort: 'total_ms', desc: true }} /></Section>}
    </div>
  )
}
