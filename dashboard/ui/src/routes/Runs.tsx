import { DataGrid } from '@/components/DataGrid'
import { Tabs, useTab } from '@/components/primitives'

const VIEWS = ['runs', 'rounds']

export function Runs() {
  const view = useTab(VIEWS)
  return (
    <div>
      <h1 className="mb-4 font-semibold">Runs</h1>
      <Tabs views={VIEWS} />
      {view === 'rounds' ? <DataGrid id="rounds" url="/api/rounds" live /> : <DataGrid id="runs" url="/api/runs" columns={['run', 'country', 'state', 'started_at', 'end_reason', 'game_to', 'snapshots', 'actions', 'invalid', 'unverified']} link={(col, cell, row) => ['snapshots', 'actions'].includes(col.name) && cell.num != null ? `/runs/${row[0].ref!.id}?view=${col.name}` : undefined} live />}
    </div>
  )
}
