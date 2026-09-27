import { Link, useParams, useSearchParams } from 'react-router-dom'
import { AsOf, useAsOf } from '@/components/AsOf'
import { DataGrid } from '@/components/DataGrid'
import { SeriesChart } from '@/components/SeriesChart'

export function usePlots() {
  const [params, setParams] = useSearchParams()
  const plots = params.getAll('plot')
  const set = (list: string[]) => {
    const next = new URLSearchParams(params)
    next.delete('plot')
    list.forEach((p) => next.append('plot', p))
    setParams(next, { replace: true })
  }
  return { plots, add: (p: string) => !plots.includes(p) && set([...plots, p]), remove: (p: string) => set(plots.filter((x) => x !== p)) }
}

export function Plots({ run, plots, remove }: { run: number; plots: string[]; remove: (p: string) => void }) {
  if (!plots.length) return null
  return (
    <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
      {plots.map((p) => {
        const [table, column, ...filters] = p.split('|')
        return <SeriesChart key={p} run={run} table={table} column={column} filters={filters} title={`${table}.${column} ${filters.join(' ')}`} onRemove={() => remove(p)} />
      })}
    </div>
  )
}

export function Table() {
  const params = useParams()
  const run = Number(params.run)
  const table = params.table!
  const a = useAsOf()
  const plot = usePlots()
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-3 text-sm">
        <Link className="linka num text-xs" to={`/runs/${run}?view=tables`}>
          run {run}
        </Link>
        <h1 className="num font-semibold">{table}</h1>
        <Link className="linka text-xs" to={`/schema?schema.f=table:${table}`}>
          schema
        </Link>
      </div>
      <Plots run={run} plots={plot.plots} remove={plot.remove} />
      <DataGrid
        id="t"
        url={`/api/runs/${run}/tables/${table}`}
        query={{ seq: a.seq, versions: a.versions }}
        toolbar={<AsOf versions />}
        onPlot={(column, filters) => plot.add([table, column, ...filters].join('|'))}
        live
      />
    </div>
  )
}
