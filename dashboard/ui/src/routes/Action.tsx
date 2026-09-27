import { Link, useParams } from 'react-router-dom'
import { DataGrid, Record } from '@/components/DataGrid'
import { Section } from '@/components/primitives'
import { useApi, type Grid } from '@/lib/api'

export function Action() {
  const params = useParams()
  const run = Number(params.run)
  const n = Number(params.n)
  const one = useApi<Grid>(`/api/runs/${run}/actions?f=n:${n}`)
  const before = one.data?.rows[0]?.[one.data.columns.findIndex((c) => c.name === 'before_seq')]?.ref?.id
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3 text-sm">
        <Link className="linka num text-xs" to={`/runs/${run}?view=actions`}>
          run {run}
        </Link>
        <Link className="linka num text-xs" to={`/runs/${run}/actions/${n - 1}`}>
          {n - 1}
        </Link>
        <h1 className="num font-semibold">action {n}</h1>
        <Link className="linka num text-xs" to={`/runs/${run}/actions/${n + 1}`}>
          {n + 1}
        </Link>
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <Section title="loop_action">
          <DataGrid id="a" url={`/api/runs/${run}/actions`} fixed={[`n:${n}`]} render={(g) => <Record grid={g} />} />
        </Section>
        {before !== undefined && (
          <Section title={`loop_action with before_seq ${before}`}>
            <DataGrid id="batch" url={`/api/runs/${run}/actions`} fixed={[`before_seq:${before}`]} initial={{ sort: 'n', desc: false }} />
          </Section>
        )}
      </div>
    </div>
  )
}
