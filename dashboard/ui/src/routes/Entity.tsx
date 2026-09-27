import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AsOf, useAsOf } from '@/components/AsOf'
import { DataGrid } from '@/components/DataGrid'
import { Loading } from '@/components/primitives'
import { useApi, type S } from '@/lib/api'
import { n } from '@/lib/format'
import { Plots, usePlots } from '@/routes/Table'

function Fold({ title, rows, open: initial, children }: { title: ReactNode; rows: number; open: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(initial)
  return (
    <section>
      <button onClick={() => setOpen(!open)} className="hover:text-fg mb-1 flex items-center gap-1.5 text-sm">
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        <span className="num font-semibold">{title}</span>
        <span className="text-dim num text-2xs">{n(rows)} rows</span>
      </button>
      {open && children}
    </section>
  )
}

export function Entity() {
  const params = useParams()
  const run = Number(params.run)
  const kind = params.kind!
  const id = Number(params.id)
  const a = useAsOf()
  const plot = usePlots()
  const state = useApi<S['EntityInfo']>(`/api/runs/${run}/entities/${kind}/${id}`, { live: true })
  const onPlot = (table: string) => (column: string, filters: string[]) => plot.add([table, column, ...filters].join('|'))
  return (
    <Loading state={state}>
      {(d) => (
        <div className="space-y-4">
          <div className="flex flex-wrap items-baseline gap-3 text-sm">
            <Link className="linka num text-xs" to={`/runs/${run}`}>
              run {run}
            </Link>
            <Link className="linka num text-xs" to={`/runs/${run}/entities/${kind}`}>
              {kind}
            </Link>
            <h1 className="num font-semibold">{d.ref.label ?? id}</h1>
            <span className="text-dim num text-xs">id {id}</span>
            <span className="text-dim num text-xs">
              first seen <Link className="linka" to={`/runs/${run}/snapshots/${d.first_seq}`}>{d.first_seq}</Link>
            </span>
            <span className="text-dim text-xs">{d.present ? 'present' : 'gone'}</span>
            <AsOf />
          </div>
          <Plots run={run} plots={plot.plots} remove={plot.remove} />
          {d.owned
            .filter((t) => t.rows)
            .map((t) => (
              <Fold key={t.table} title={<Link className="linka" to={`/runs/${run}/tables/${t.table}?t.f=${kind}:${id}${t.keyed ? '' : '&versions=1'}`}>{t.table}</Link>} rows={t.rows} open>
                <DataGrid
                  id={t.table}
                  url={`/api/runs/${run}/tables/${t.table}`}
                  query={{ seq: a.seq, versions: !t.keyed }}
                  fixed={[`${kind}:${id}`]}
                  initial={t.keyed ? undefined : { sort: 'seq', desc: true }}
                  onPlot={onPlot(t.table)}
                  live
                />
              </Fold>
            ))}
          {d.references.map((r) => (
            <Fold key={`${r.table}.${r.column}`} title={`${r.table}.${r.column}`} rows={r.rows} open={false}>
              <DataGrid id={`${r.table}.${r.column}`} url={`/api/runs/${run}/tables/${r.table}`} query={{ seq: a.seq }} fixed={[`${r.column}:${id}`]} live />
            </Fold>
          ))}
          {d.actions > 0 && (
            <Fold title="loop_action" rows={d.actions} open>
              <DataGrid id="acted" url={`/api/runs/${run}/entities/${kind}/${id}/actions`} live />
            </Fold>
          )}
        </div>
      )}
    </Loading>
  )
}
