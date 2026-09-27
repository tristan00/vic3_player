import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { DataGrid, Record } from '@/components/DataGrid'
import { Neighbors } from '@/components/Neighbors'
import { ErrorState, Loading, Section, Tabs, useTab } from '@/components/primitives'
import { SeriesChart, SeriesView } from '@/components/SeriesChart'
import { useApi, type S } from '@/lib/api'
import { cn } from '@/lib/format'

const VIEWS = ['record', 'actions', 'blocks', 'snapshots', 'countries', 'trade', 'entities', 'tables', 'charts', 'timing']

function Outcomes({ run }: { run: number }) {
  const state = useApi<S['Series'][]>(`/api/runs/${run}/outcomes`, { live: true })
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />
  const found = state.data ?? [null, null, null]
  return (
    <div className="mb-4 grid gap-3 lg:grid-cols-3">
      {found.map((s, i) => (
        <SeriesView key={i} run={run} series={s} title={s?.table ?? ''} height={170} />
      ))}
    </div>
  )
}

function RecordView({ run }: { run: number }) {
  return (
    <div className="space-y-5">
      <DataGrid id="run" url={`/api/runs/${run}/record`} live render={(g) => <Record grid={g} />} />
      <Section title="actions by group">
        <DataGrid id="groups" url={`/api/runs/${run}/groups`} live />
      </Section>
      <Section title="run_game_rule">
        <DataGrid id="rules" url="/api/meta/run_game_rule" fixed={[`run_id:${run}`]} />
      </Section>
    </div>
  )
}

function Charts({ run }: { run: number }) {
  const [params, setParams] = useSearchParams()
  const shown = params.getAll('chart')
  const choices = useApi<S['SeriesChoice'][]>('/api/series')
  const [pick, setPick] = useState('')
  const set = (list: string[]) => {
    const next = new URLSearchParams(params)
    next.delete('chart')
    list.forEach((c) => next.append('chart', c))
    setParams(next, { replace: true })
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <select value={pick} onChange={(e) => setPick(e.target.value)} className="border-line num max-w-md rounded border px-2 py-1 text-xs">
          <option value="">player series</option>
          {choices.data?.map((c) => (
            <option key={`${c.table}.${c.column}`} value={`${c.table}.${c.column}`}>
              {c.table}.{c.column}
            </option>
          ))}
        </select>
        <button disabled={!pick || shown.includes(pick)} onClick={() => set([...shown, pick])} className="border-line rounded border px-2 py-1 text-xs disabled:opacity-40">
          add
        </button>
      </div>
      <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
        {shown.map((c) => {
          const [table, column] = c.split('.')
          return <SeriesChart key={c} run={run} table={table} column={column} player onRemove={() => set(shown.filter((x) => x !== c))} />
        })}
      </div>
    </div>
  )
}

export function Run() {
  const run = Number(useParams().run)
  const view = useTab(VIEWS)
  const info = useApi<S['RunInfo']>(`/api/runs/${run}`, { live: true })
  return (
    <Loading state={info}>
      {(d) => (
        <div>
          <div className="mb-3 flex flex-wrap items-baseline gap-x-3 text-sm">
            <Neighbors previous={d.previous} next={d.next} to={(n) => `/runs/${n}`}>
              <h1 className="num font-semibold">run {run}</h1>
            </Neighbors>
            <span className="num">{d.country}</span>
            <span className={cn('text-xs', d.state !== 'ended' && 'text-accent')}>{d.state}</span>
            <span className="text-dim num text-xs">last snapshot {d.last_seq ?? '∅'}</span>
            <Link className="linka text-xs" to={`/policy/runs/${run}`}>
              policy
            </Link>
          </div>
          <Outcomes run={run} />
          <Tabs views={VIEWS} />
          {view === 'record' && <RecordView run={run} />}
          {view === 'actions' && <DataGrid id="actions" url={`/api/runs/${run}/actions`} live />}
          {view === 'blocks' && <DataGrid id="blocks" url={`/api/runs/${run}/blocks`} live />}
          {view === 'snapshots' && <DataGrid id="snapshots" url="/api/meta/snapshot" fixed={[`run_id:${run}`]} initial={{ sort: 'seq', desc: true }} live />}
          {view === 'countries' && <DataGrid id="countries" url={`/api/runs/${run}/entities/country`} live />}
          {view === 'trade' && (
            <div className="space-y-5">
              <Section title="market">
                <DataGrid id="markets" url={`/api/runs/${run}/entities/market`} live />
              </Section>
              <Section title="market_goods">
                <DataGrid id="goods" url={`/api/runs/${run}/tables/market_goods`} live />
              </Section>
              <Section title="world_market_hub">
                <DataGrid id="hubs" url={`/api/runs/${run}/tables/world_market_hub`} live />
              </Section>
              <Section title="world_market_price_channel">
                <DataGrid id="channels" url={`/api/runs/${run}/tables/world_market_price_channel`} live />
              </Section>
              <Section title="world_market_price_sample">
                <DataGrid id="world_prices" url={`/api/runs/${run}/tables/world_market_price_sample`} initial={{ sort: 'n', desc: true }} live />
              </Section>
            </div>
          )}
          {view === 'entities' && <DataGrid id="kinds" url={`/api/runs/${run}/kinds`} limit={100} />}
          {view === 'tables' && <DataGrid id="tables" url={`/api/runs/${run}/tables`} limit={500} />}
          {view === 'charts' && <Charts run={run} />}
          {view === 'timing' && (
            <div className="space-y-5">
              <Section title="run_timing">
                <DataGrid id="run_timing" url="/api/meta/run_timing" fixed={[`run_id:${run}`]} initial={{ sort: 'total_ms', desc: true }} limit={500} live />
              </Section>
              <Section title="snapshot_timing">
                <DataGrid id="snapshot_timing" url="/api/meta/snapshot_timing" fixed={[`run_id:${run}`]} initial={{ sort: 'seq', desc: true }} live />
              </Section>
            </div>
          )}
        </div>
      )}
    </Loading>
  )
}
