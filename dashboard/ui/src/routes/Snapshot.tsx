import { Link, useParams, useSearchParams } from 'react-router-dom'
import { DataGrid, Record } from '@/components/DataGrid'
import { Section } from '@/components/primitives'

export function Snapshot() {
  const params = useParams()
  const run = Number(params.run)
  const seq = Number(params.seq)
  const [search] = useSearchParams()
  const table = search.get('table')
  const at = (s: number) => `/runs/${run}/snapshots/${s}`
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3 text-sm">
        <Link className="linka num text-xs" to={`/runs/${run}?view=snapshots`}>
          run {run}
        </Link>
        <Link className="linka num text-xs" to={at(seq - 1)}>
          {seq - 1}
        </Link>
        <h1 className="num font-semibold">snapshot {seq}</h1>
        <Link className="linka num text-xs" to={at(seq + 1)}>
          {seq + 1}
        </Link>
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <Section title="snapshot">
          <DataGrid id="s" url="/api/meta/snapshot" fixed={[`run_id:${run}`, `seq:${seq}`]} render={(g) => <Record grid={g} />} />
        </Section>
        <div className="min-w-0 space-y-5">
          <Section title="loop_action with before_seq">
            <DataGrid id="chosen" url={`/api/runs/${run}/actions`} fixed={[`before_seq:${seq}`]} />
          </Section>
          <Section title="loop_action with after_seq">
            <DataGrid id="executed" url={`/api/runs/${run}/actions`} fixed={[`after_seq:${seq}`]} />
          </Section>
          <Section title="rows recorded at this snapshot">
            <DataGrid
              id="changed"
              url={`/api/runs/${run}/snapshots/${seq}/tables`}
              limit={500}
              link={(col, cell) => (col.kind === 'table' ? `${at(seq)}?table=${cell.text}` : undefined)}
            />
          </Section>
        </div>
      </div>
      {table && (
        <Section title={<span className="num">{table}</span>}>
          <DataGrid key={table} id="rows" url={`/api/runs/${run}/snapshots/${seq}/tables/${table}`} />
        </Section>
      )}
    </div>
  )
}
