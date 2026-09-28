import { Link, useParams } from 'react-router-dom'
import { DataGrid, Record } from '@/components/DataGrid'
import { Neighbors } from '@/components/Neighbors'
import { Section } from '@/components/primitives'
import { useApi, type Grid, type S } from '@/lib/api'

export function Action() {
  const params = useParams()
  const run = Number(params.run)
  const n = Number(params.n)
  const one = useApi<Grid>(`/api/runs/${run}/actions?f=n:${n}`)
  const info = useApi<S['RunInfo']>(`/api/runs/${run}`, { live: true })
  const before = one.data?.rows[0]?.[one.data.columns.findIndex((c) => c.name === 'before_seq')]?.ref?.id
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3 text-sm">
        <Link className="linka num text-xs" to={`/runs/${run}?view=actions`}>
          run {run}
        </Link>
        {info.data && (
          <Neighbors previous={n > 1 ? n - 1 : null} next={info.data.last_action !== null && n < info.data.last_action ? n + 1 : null} to={(k) => `/runs/${run}/actions/${k}`}>
            <h1 className="num font-semibold">action {n}</h1>
          </Neighbors>
        )}
      </div>
      <div className="space-y-6">
        <Section title="Action details and targets">
          <DataGrid id="a" url={`/api/runs/${run}/actions`} fixed={[`n:${n}`]} render={(g) => <Record grid={g} />} />
        </Section>
        {before !== undefined && (
          <Section title={`Actions from snapshot ${before}`}>
            <DataGrid id="batch" url={`/api/runs/${run}/actions`} fixed={[`before_seq:${before}`]} initial={{ sort: 'n', desc: false }} />
          </Section>
        )}
      </div>
    </div>
  )
}
