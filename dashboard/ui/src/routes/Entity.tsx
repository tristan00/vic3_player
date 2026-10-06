import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { AsOf, useAsOf } from '@/components/AsOf'
import { DataGrid, Record } from '@/components/DataGrid'
import { Loading, Tabs, useTab } from '@/components/primitives'
import { Treaty } from '@/components/Treaty'
import { qs, useApi, type S } from '@/lib/api'
import { label, n } from '@/lib/format'
import { Plots, usePlots } from '@/routes/Table'

function Fold({ title, rows, open: initial, children }: { title: ReactNode; rows: number; open: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(initial)
  return (
    <section>
      <div className="mb-2 flex items-center gap-2"><button aria-expanded={open} aria-label={`${open ? 'Collapse' : 'Expand'} table`} onClick={() => setOpen(!open)} className="hover:text-fg flex items-center gap-1.5 text-sm">
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
      </button><span className="font-semibold">{title}</span>
        <span className="text-dim num text-2xs">{n(rows)} recorded rows</span>
      </div>
      {open && children}
    </section>
  )
}

export function Entity() {
  const view = useTab(['details', 'history', 'relationships', 'actions'])
  const [search, setSearch] = useSearchParams()
  const params = useParams()
  const run = Number(params.run)
  const kind = params.kind!
  const id = Number(params.id)
  const a = useAsOf()
  const plot = usePlots()
  const state = useApi<S['EntityInfo']>(`/api/runs/${run}/entities/${kind}/${id}${qs({ seq: a.seq })}`, { live: true })
  const onPlot = (table: string) => (column: string, filters: string[]) => plot.add([table, column, ...filters].join('|'))
  return (
    <Loading state={state}>
      {(d) => (
        <div className="space-y-4">
          <div className="flex flex-wrap items-baseline gap-3 text-sm">
            <Link className="linka num text-xs" to={`/runs/${run}`}>
              run {run}
            </Link>
            <Link className="linka num text-xs" to={`/runs/${run}/entities/${kind}${a.seq ? `?seq=${a.seq}` : ''}`}>
              {kind}
            </Link>
            <h1 className="num font-semibold">{d.ref.label ?? id}</h1>
            <span className="text-dim num text-xs">id {id}</span>
            <span className="text-dim num text-xs">
              first seen <Link className="linka" to={`/runs/${run}/snapshots/${d.first_seq}`}>{d.first_seq}</Link>
            </span>
            <span className="text-dim text-xs">{d.present ? 'present at latest snapshot' : 'gone at latest snapshot'}</span>
            <AsOf />
          </div>
          <Tabs views={['details', 'history', 'relationships', 'actions']} />
          <Plots run={run} plots={plot.plots} remove={plot.remove} />
          {view === 'details' && kind === 'treaty' && <Treaty treaty={d.treaty} seq={a.seq} />}
          {(view === 'details' || view === 'history') && <label className="flex flex-wrap items-center gap-3">Entity data<select aria-label="Entity data" value={search.get('table') ?? d.owned.find((t) => t.rows)?.table ?? ''} onChange={(e) => { const next = new URLSearchParams(search); next.set('table', e.target.value); setSearch(next) }}>
            {d.owned.filter((t) => t.rows).map((t) => <option key={t.table} value={t.table}>{label(t.table)} · {n(t.rows)} recorded rows</option>)}
          </select></label>}
          {(view === 'details' || view === 'history') && d.owned
            .filter((t) => t.rows && t.table === (search.get('table') ?? d.owned.find((t) => t.rows)?.table))
            .map((t) => (
              <Fold key={`${view}.${t.table}`} title={<Link className="linka" to={`/runs/${run}/tables/${t.table}?t.f=${kind}:${id}${view === 'history' ? '&versions=1' : ''}${a.seq ? `&seq=${a.seq}` : ''}`}>{label(t.table)}</Link>} rows={t.rows} open>
                <DataGrid
                  id={`${view}.${t.table}`}
                  url={`/api/runs/${run}/tables/${t.table}`}
                  query={{ seq: a.seq, versions: view === 'history' }}
                  fixed={[`${kind}:${id}`]}
                  initial={view === 'history' || t.kind === 'sample' ? { sort: 'seq', desc: true } : undefined}
                  limit={view === 'details' && t.kind === 'sample' ? 1 : 25}
                  render={view === 'details' && !t.keyed ? (g) => <Record grid={g} onPlot={(column) => onPlot(t.table)(column, [`${kind}:${id}`])} /> : undefined}
                  onPlot={onPlot(t.table)}
                  live
                />
              </Fold>
            ))}
          {view === 'relationships' && d.references.map((r) => (
            <Fold key={`${r.table}.${r.column}`} title={<Link className="linka" to={`/runs/${run}/tables/${r.table}?t.f=${r.column}:${id}${a.seq ? `&seq=${a.seq}` : ''}`}>{label(r.table)} · {label(r.column)}</Link>} rows={r.rows} open={false}>
              <DataGrid id={`${r.table}.${r.column}`} url={`/api/runs/${run}/tables/${r.table}`} query={{ seq: a.seq }} fixed={[`${r.column}:${id}`]} live />
            </Fold>
          ))}
          {view === 'relationships' && !d.references.length && <p className="text-dim">No recorded relationships.</p>}
          {view === 'actions' && (
            <Fold title="Actions targeting this entity" rows={d.actions} open>
              <DataGrid id="acted" url={`/api/runs/${run}/entities/${kind}/${id}/actions`} live />
            </Fold>
          )}
        </div>
      )}
    </Loading>
  )
}
