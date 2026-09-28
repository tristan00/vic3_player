import { Link, useNavigate, useParams } from 'react-router-dom'
import { AsOf, useAsOf } from '@/components/AsOf'
import { DataGrid } from '@/components/DataGrid'
import { label } from '@/lib/format'

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
        <h1 className="font-semibold capitalize">{label(kind)}</h1>
      </div>
      <DataGrid
        id="e"
        columnGroup={kind}
        url={`/api/runs/${run}/entities/${kind}`}
        query={{ seq: a.seq, gone: a.gone }}
        toolbar={<AsOf gone />}
        onRow={(row) => row[0].ref && navigate(`/runs/${run}/entities/${kind}/${row[0].ref.id}${a.seq ? `?seq=${a.seq}` : ''}`)}
        live
      />
    </div>
  )
}
