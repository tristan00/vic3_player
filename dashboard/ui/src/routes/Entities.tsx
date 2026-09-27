import { Link, useNavigate, useParams } from 'react-router-dom'
import { AsOf, useAsOf } from '@/components/AsOf'
import { DataGrid } from '@/components/DataGrid'

export function Entities() {
  const params = useParams()
  const run = Number(params.run)
  const kind = params.kind!
  const a = useAsOf()
  const navigate = useNavigate()
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-3 text-sm">
        <Link className="linka num text-xs" to={`/runs/${run}?view=entities`}>
          run {run}
        </Link>
        <h1 className="num font-semibold">{kind}</h1>
      </div>
      <DataGrid
        id="e"
        url={`/api/runs/${run}/entities/${kind}`}
        query={{ seq: a.seq, gone: a.gone }}
        toolbar={<AsOf gone />}
        onRow={(row) => row[0].ref && navigate(`/runs/${run}/entities/${kind}/${row[0].ref.id}`)}
        live
      />
    </div>
  )
}
