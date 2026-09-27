import { DataGrid } from '@/components/DataGrid'
import { Tabs, useTab } from '@/components/primitives'

const VIEWS = ['runs', 'rounds']

export function Runs() {
  const view = useTab(VIEWS)
  return (
    <div>
      <Tabs views={VIEWS} />
      {view === 'rounds' ? <DataGrid id="rounds" url="/api/rounds" live /> : <DataGrid id="runs" url="/api/runs" live />}
    </div>
  )
}
