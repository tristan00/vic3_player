import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { DataGrid, Record } from '@/components/DataGrid'
import { Card, Loading, Section, Tabs, useTab } from '@/components/primitives'
import { SeriesChart } from '@/components/SeriesChart'
import { useApi, type S } from '@/lib/api'
import { cn, num } from '@/lib/format'

const VIEWS = ['record', 'actions', 'blocks', 'snapshots', 'countries', 'trade', 'entities', 'tables', 'charts']
const PARTS: (keyof S['RewardPart'])[] = ['weight', 'change', 'divisor', 'discounted', 'scale', 'normalized', 'contribution']

function Reward({ info }: { info: S['RunInfo'] }) {
  if (!info.reward_parts.length) return <Card className="text-dim px-3 py-2 text-xs">not scored</Card>
  const total = info.reward_parts.reduce((a, p) => a + p.contribution, 0)
  return (
    <Card className="overflow-hidden">
      <table className="text-xs">
        <thead>
          <tr className="border-line text-dim border-b">
            <th className="px-2 py-1 text-left font-medium">component</th>
            <th className="px-2 py-1 text-right font-medium">years</th>
            {PARTS.map((p) => (
              <th key={p} className="px-2 py-1 text-right font-medium">
                {p}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {info.reward_parts.map((p) => (
            <tr key={p.component} className="border-line/60 border-b">
              <td className="px-2 py-0.5">{p.component}</td>
              <td className="num px-2 py-0.5 text-right">{num(info.reward_years as number)}</td>
              {PARTS.map((k) => (
                <td key={k} className="num px-2 py-0.5 text-right">
                  {num(p[k] as number)}
                </td>
              ))}
            </tr>
          ))}
          <tr>
            <td className="px-2 py-0.5">reward</td>
            <td colSpan={PARTS.length} />
            <td className="num px-2 py-0.5 text-right font-semibold">{num(total)}</td>
          </tr>
        </tbody>
      </table>
    </Card>
  )
}

function RecordView({ run, info }: { run: number; info: S['RunInfo'] }) {
  const fixed = [`run_id:${run}`]
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
      <Section title="run">
        <DataGrid id="run" url="/api/meta/run" fixed={fixed} live render={(g) => <Record grid={g} />} />
      </Section>
      <div className="min-w-0 space-y-5">
        <Section title="reward">
          <Reward info={info} />
        </Section>
        <Section title="actions by group">
          <DataGrid id="groups" url={`/api/runs/${run}/groups`} live />
        </Section>
        <Section title="run_advisor">
          <DataGrid id="advisor" url="/api/meta/run_advisor" fixed={fixed} />
        </Section>
        <Section title="smac_proposal">
          <DataGrid id="proposal" url="/api/meta/smac_proposal" fixed={fixed} />
        </Section>
        <Section title="pick_model">
          <DataGrid id="model" url="/api/meta/pick_model" fixed={fixed} />
        </Section>
        <Section title="run_weight">
          <DataGrid id="weights" url="/api/meta/run_weight" fixed={fixed} initial={{ sort: 'weight', desc: true }} />
        </Section>
        <Section title="run_param_weight">
          <DataGrid id="param_weights" url="/api/meta/run_param_weight" fixed={fixed} />
        </Section>
        <Section title="run_game_rule">
          <DataGrid id="rules" url="/api/meta/run_game_rule" fixed={fixed} />
        </Section>
      </div>
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
            <Link className="linka text-xs" to={`/runs/${run - 1}`}>
              {run - 1}
            </Link>
            <h1 className="num font-semibold">run {run}</h1>
            <Link className="linka text-xs" to={`/runs/${run + 1}`}>
              {run + 1}
            </Link>
            <span className="num">{d.country}</span>
            <span className={cn('text-xs', d.state !== 'ended' && 'text-accent')}>{d.state}</span>
            <span className="text-dim num text-xs">last snapshot {d.last_seq ?? '∅'}</span>
          </div>
          <Tabs views={VIEWS} />
          {view === 'record' && <RecordView run={run} info={d} />}
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
        </div>
      )}
    </Loading>
  )
}
