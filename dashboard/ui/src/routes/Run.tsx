import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ActionTable } from '@/components/ActionTable'
import { BlockTable } from '@/components/BlockTable'
import { LineChart, StatusBar, StatusLegend } from '@/components/charts'
import { Card, CountText, EndChip, Loading, KV, Pager, RateText, RefLink, Section, Select, StateChip, statusTotal, Tabs, Tile, useTab } from '@/components/primitives'
import { SeriesChart } from '@/components/SeriesChart'
import { RunCountries } from '@/routes/RunCountries'
import { RunTrade } from '@/routes/RunTrade'
import { Table, type Col } from '@/components/Table'
import { qs, useApi, type S } from '@/lib/api'
import { ago, duration, gameYears, label, ms, n, STATUS_LABEL, STATUSES, when } from '@/lib/format'

const VIEWS = [
  { key: 'overview', label: 'overview' },
  { key: 'decisions', label: 'decisions' },
  { key: 'actions', label: 'actions' },
  { key: 'snapshots', label: 'snapshots' },
  { key: 'countries', label: 'countries' },
  { key: 'trade', label: 'trade' },
  { key: 'entities', label: 'entities' },
]
const DEFAULT_SERIES = [
  'player_treasury.balance',
  'player_budget_line.interest',
  'country_gdp_sample.gdp',
  'player_prestige_sample.prestige',
  'country_population_sample.population',
  'player_literacy_sample.literacy',
  'player_radicals_sample.radicals',
]

function Header({ d }: { d: S['RunDetail'] }) {
  const r = d.run
  const [rules, setRules] = useState(false)
  return (
    <div className="mb-5 space-y-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-xl font-semibold tracking-tight">run {r.run_id}</h1>
        {r.state === 'ended' ? <EndChip reason={r.end_reason} /> : <StateChip state={r.state} />}
        <span className="text-sm">
          playing <RefLink run={r.run_id} refd={d.player} /> <span className="num text-dim">{r.tag}</span>
        </span>
        <span className="text-dim text-xs">
          round{' '}
          <Link className="linka num" to={`/runs?round=${r.round}`}>
            {r.round}
          </Link>{' '}
          · started {when(r.started_at)}
          {r.ended_at && ` · ended ${ago(r.ended_at)}`}
        </span>
      </div>
      {r.end_detail && <Card className="border-invalid px-3 py-2 text-xs">{r.end_detail}</Card>}
      <Card className="grid gap-x-10 gap-y-3 px-4 py-3 md:grid-cols-3">
        <KV
          items={[
            ['world', <span key="w"><span className="text-dim">{r.kind}</span> <span className="num">{r.world}</span></span>],
            ['world id / ruleset', <span key="i" className="num">{d.world_id} / {d.ruleset_id}</span>],
            ['generated with', d.world_seed === null ? 'vanilla map' : <span key="g" className="num">seed {d.world_seed} · {d.countries} countries · {d.states} states · tech {d.tech} · pop {d.pop}</span>],
            ['advisors', r.advisors.join(', ')],
            ['profile', d.profile],
          ]}
        />
        <KV
          items={[
            ['launch seed', <span key="c" className="num">{d.cli_seed}</span>],
            ['run seed', <span key="s" className="num">{d.run_seed}</span>],
            ['game rng seed', <span key="g" className="num">{d.custom_rng_seed || 'none set'}</span>],
            ['world pool', d.pool ? `${d.pool} workers` : 'none'],
            ['round asked for', `${n(d.runs_requested)} runs`],
          ]}
        />
        <KV
          items={[
            ['budget', `${r.years} game years or ${duration(r.minutes * 60)}`],
            ['game speed', String(d.game_speed)],
            ['step now', r.state === 'ended' ? <span key="e" className="text-dim">ended</span> : <code key="p">{d.progress_step} · {duration(d.progress_age_s)}</code>],
            ['longest step', d.longest_step ? <code key="l">{d.longest_step} · {ms(d.longest_step_ms)}</code> : '—'],
          ]}
        />
        <div className="md:col-span-3">
          <button className="text-dim hover:text-fg text-2xs" onClick={() => setRules(!rules)}>
            {rules ? 'hide' : 'show'} {d.rules.length} game rules
          </button>
          {rules && <div className="num mt-1 text-2xs leading-relaxed">{d.rules.join(' · ')}</div>}
        </div>
        <div className="md:col-span-3">
          <div className="text-dim text-2xs">action weights that differ from 1 · every other action weighs 1</div>
          <div className="num mt-0.5 text-2xs leading-relaxed">{d.weights.length ? d.weights.map((w) => `${w.action} ${w.weight}`).join(' · ') : 'none'}</div>
          <div className="text-dim mt-1 text-2xs">parameter weights, applied to the choice among an action’s options · every other option weighs 1</div>
          <div className="num mt-0.5 text-2xs leading-relaxed">{d.param_weights.length ? d.param_weights.map((w) => `${w.action} ${w.param}=${w.value} ${w.weight}`).join(' · ') : 'none'}</div>
        </div>
      </Card>
    </div>
  )
}

function Overview({ d }: { d: S['RunDetail'] }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [adding, setAdding] = useState('')
  const r = d.run
  const chosen = params.get('series') ? params.get('series')!.split(',').filter(Boolean) : DEFAULT_SERIES
  const setSeries = (list: string[]) => {
    const next = new URLSearchParams(params)
    next.set('series', list.join(','))
    setParams(next, { replace: true })
  }
  const span = r.game_from && r.game_to ? r.game_to.hours - r.game_from.hours : 0
  const groupCols: Col<S['GroupStatus']>[] = [
    { key: 'group', label: 'group', value: (g) => g.group, render: (g) => g.group },
    { key: 'total', label: 'actions', align: 'right', value: (g) => g.total, render: (g) => n(g.total) },
    ...STATUSES.map((s) => ({
      key: s,
      label: STATUS_LABEL[s],
      align: 'right' as const,
      value: (g: S['GroupStatus']) => g.statuses.find((x) => x.status === s)!.count,
      render: (g: S['GroupStatus']) => {
        const c = g.statuses.find((x) => x.status === s)!.count
        return c ? n(c) : <span className="text-muted">0</span>
      },
    })),
    { key: 'bar', label: 'mix', render: (g) => <div className="w-48"><StatusBar counts={g.statuses} onPick={(s) => navigate(`/runs/${r.run_id}?view=actions&group=${g.group}&status=${s}`)} /></div> },
  ]
  return (
    <div className="space-y-8">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Tile label="wall time" value={duration(r.wall_s)} sub={`of ${duration(r.minutes * 60)} budget`} />
        <Tile label="game time" value={gameYears(span)} sub={`${r.game_from?.text ?? '—'} → ${r.game_to?.text ?? '—'}`} />
        <Tile label="actions" value={n(r.actions)} sub={<RateText rate={r.done} />} />
        <Tile label="snapshots" value={n(r.snapshots)} sub={`${n(d.entities.reduce((a, e) => a + e.ever, 0))} entities seen`} />
        <Tile label="median snapshot read" value={ms(median(d.read_ms))} sub={`slowest ${ms(Math.max(0, ...d.read_ms))}`} />
      </div>

      <Section title="how its actions fared" scope={{ text: `every action run ${r.run_id} logged`, detail: `${n(statusTotal(d.statuses))} actions; click a segment to list those actions` }}>
        <Card className="mb-3 space-y-3 px-4 py-3">
          <StatusBar counts={d.statuses} height={14} onPick={(s) => navigate(`/runs/${r.run_id}?view=actions&status=${s}`)} />
          <StatusLegend counts={d.statuses} />
        </Card>
        <Table rows={d.groups} cols={groupCols} rowKey={(g) => g.group} onRow={(g) => navigate(`/runs/${r.run_id}?view=actions&group=${g.group}`)} empty="no action logged yet" />
      </Section>

      <Section
        title="the player over the run"
        scope={{ text: `values the recorder kept for the player in run ${r.run_id}`, detail: 'dated series step between changes; sample series are the trend buffers the game keeps; click a dated point to open its snapshot' }}
        right={
          <div className="flex items-center gap-2">
            <select value={adding} onChange={(e) => setAdding(e.target.value)} className="border-line max-w-72 rounded-md border px-2 py-1 text-xs">
              <option value="">add a series…</option>
              {d.series
                .filter((s) => !chosen.includes(`${s.table}.${s.column}`))
                .map((s) => (
                  <option key={s.label} value={`${s.table}.${s.column}`}>
                    {s.label}
                  </option>
                ))}
            </select>
            <button disabled={!adding} className="border-line rounded-md border px-2 py-1 text-xs" onClick={() => { setSeries([...chosen, adding]); setAdding('') }}>
              add
            </button>
          </div>
        }
      >
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {chosen.map((key) => {
            const [table, column] = key.split('.')
            return <SeriesChart key={key} run={r.run_id} table={table} column={column} onRemove={() => setSeries(chosen.filter((c) => c !== key))} />
          })}
        </div>
      </Section>

      <Section title="snapshot read time" scope={{ text: `every snapshot of run ${r.run_id}`, detail: 'how long the recorder took to read the game; click a point to open that snapshot' }}>
        <Card className="px-2 py-2">
          <LineChart xs={d.read_seq} ys={d.read_ms} height={150} xFormat={(x) => `#${n(x)}`} yFormat={(y) => ms(y)} tip={(i) => `snapshot ${d.read_seq[i]}`} onPick={(i) => navigate(`/runs/${r.run_id}/snapshots/${d.read_seq[i]}`)} />
        </Card>
      </Section>
    </div>
  )
}

function median(values: number[]): number | null {
  if (!values.length) return null
  const s = [...values].sort((a, b) => a - b)
  return s[Math.floor(s.length / 2)]
}

function Actions({ run, live }: { run: number; live: boolean }) {
  const [params, setParams] = useSearchParams()
  const get = (k: string) => params.get(k) ?? ''
  const offset = Number(get('offset') || 0)
  const limit = 100
  const state = useApi<S['ActionLog']>(`/api/runs/${run}/actions${qs({ offset, limit, action: get('action'), group: get('group'), status: get('status') })}`, { live })
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    v ? next.set(k, v) : next.delete(k)
    if (k !== 'offset') next.delete('offset')
    setParams(next, { replace: true })
  }
  return (
    <Loading state={state} rows={14}>
      {(d) => (
        <Section title="every action" scope={d.scope}>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Card className="px-3 py-1.5">
              <CountText count={d.total} />
            </Card>
            <Select value={get('group')} onChange={(v) => set('group', v)} all="every group" options={d.groups.map((f) => ({ value: f.value, label: `${f.value} · ${n(f.count)}` }))} />
            <Select value={get('action')} onChange={(v) => set('action', v)} all="every action" options={d.actions.map((f) => ({ value: f.value, label: `${label(f.value)} · ${n(f.count)}` }))} />
            <Select value={get('status')} onChange={(v) => set('status', v)} all="every status" options={d.statuses.map((s) => ({ value: s.status, label: `${STATUS_LABEL[s.status]} · ${n(s.count)}` }))} />
            <div className="ml-auto">
              <Pager offset={offset} limit={limit} shown={d.rows.length} total={d.total.value} onOffset={(o) => set('offset', String(o))} />
            </div>
          </div>
          <ActionTable rows={d.rows} empty="no action matches these filters" why="clear a filter above" />
        </Section>
      )}
    </Loading>
  )
}

function Decisions({ run, live }: { run: number; live: boolean }) {
  const [params, setParams] = useSearchParams()
  const kind = params.get('kind') ?? 'decision'
  const offset = Number(params.get('offset') ?? 0)
  const limit = 50
  const state = useApi<S['BlockLog']>(`/api/runs/${run}/blocks${qs({ offset, limit, kind: kind === 'all' ? '' : kind })}`, { live })
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    next.set(k, v)
    if (k !== 'offset') next.delete('offset')
    setParams(next, { replace: true })
  }
  return (
    <Loading state={state} rows={12}>
      {(d) => (
        <Section title="blocks of actions" scope={d.scope}>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Card className="px-3 py-1.5">
              <CountText count={d.total} />
            </Card>
            <div className="bg-raised flex gap-0.5 rounded-md p-0.5 text-xs">
              {['decision', 'events', 'time', 'all'].map((k) => (
                <button key={k} onClick={() => set('kind', k)} className={k === kind ? 'bg-surface rounded px-2.5 py-1 font-semibold shadow-sm' : 'text-dim hover:text-fg rounded px-2.5 py-1'}>
                  {k}
                  {k !== 'all' && <span className="text-dim"> {n(d.kinds.find((f) => f.value === k)?.count ?? 0)}</span>}
                </button>
              ))}
            </div>
            <div className="ml-auto">
              <Pager offset={offset} limit={limit} shown={d.rows.length} total={d.total.value} onOffset={(o) => set('offset', String(o))} />
            </div>
          </div>
          <BlockTable run={run} rows={d.rows} empty="no block of this kind" />
        </Section>
      )}
    </Loading>
  )
}

function Snapshots({ run, live }: { run: number; live: boolean }) {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const offset = Number(params.get('offset') ?? 0)
  const limit = 100
  const state = useApi<S['SnapshotsPage']>(`/api/runs/${run}/snapshots${qs({ offset, limit })}`, { live })
  const flag = (on: boolean, word: string) => (on ? <span className="bg-warn-soft rounded px-1.5 text-2xs">{word}</span> : null)
  const cols: Col<S['SnapshotRow']>[] = [
    { key: 'seq', label: 'snapshot', align: 'right', value: (s) => s.seq, render: (s) => <Link className="linka" to={`/runs/${run}/snapshots/${s.seq}`}>{s.seq}</Link> },
    { key: 'phase', label: 'phase', value: (s) => s.phase, render: (s) => s.phase.replaceAll('_', ' ') },
    { key: 'date', label: 'game date', value: (s) => s.game_date.hours, render: (s) => <span className="num">{s.game_date.text}</span> },
    { key: 'taken', label: 'taken', value: (s) => s.taken_at, render: (s) => when(s.taken_at) },
    { key: 'read', label: 'read', align: 'right', value: (s) => s.read_ms, render: (s) => ms(s.read_ms) },
    { key: 'actions', label: 'actions ending here', align: 'right', value: (s) => s.actions, render: (s) => (s.actions ? n(s.actions) : <span className="text-muted">0</span>) },
    { key: 'speed', label: 'clock', render: (s) => (s.paused === null ? <span className="text-muted">unread</span> : s.paused ? 'paused' : `speed ${s.speed}`) },
    { key: 'ui', label: 'open windows', render: (s) => <span className="flex gap-1">{flag(s.ui_panel_open, 'panel')}{flag(s.ui_interaction_open, 'interaction')}{flag(s.ui_map_list_open, 'map list')}</span> },
  ]
  return (
    <Loading state={state} rows={14}>
      {(d) => (
        <Section title="snapshots" scope={d.scope} right={<Pager offset={offset} limit={limit} shown={d.rows.length} total={d.total.value} onOffset={(o) => setParams({ view: 'snapshots', offset: String(o) })} />}>
          <Table rows={d.rows} cols={cols} rowKey={(s) => String(s.seq)} onRow={(s) => navigate(`/runs/${run}/snapshots/${s.seq}`)} empty="no snapshot recorded" />
        </Section>
      )}
    </Loading>
  )
}

function Entities({ d }: { d: S['RunDetail'] }) {
  const navigate = useNavigate()
  const cols: Col<S['EntityKindRow']>[] = [
    { key: 'kind', label: 'entity', value: (e) => e.kind, render: (e) => <Link className="linka" to={`/runs/${d.run.run_id}/entities/${e.kind}`}>{label(e.kind)}</Link> },
    { key: 'live', label: 'present at the last snapshot', align: 'right', value: (e) => e.live, render: (e) => n(e.live) },
    { key: 'ever', label: 'ever recorded', align: 'right', value: (e) => e.ever, render: (e) => n(e.ever) },
    { key: 'tables', label: 'tables about it', align: 'right', value: (e) => e.tables, render: (e) => n(e.tables) },
  ]
  return (
    <Section title="what the recorder knows" scope={{ text: `every entity kind the recorder tracks, counted in run ${d.run.run_id}`, detail: 'ever recorded includes entities only referenced by others' }}>
      <Table rows={d.entities} cols={cols} rowKey={(e) => e.kind} onRow={(e) => navigate(`/runs/${d.run.run_id}/entities/${e.kind}`)} empty="no snapshot recorded yet" />
    </Section>
  )
}

export function Run() {
  const run = Number(useParams().run)
  const view = useTab(VIEWS)
  const state = useApi<S['RunDetail']>(`/api/runs/${run}`, { live: true })
  const live = state.data?.run.state !== 'ended'
  return (
    <Loading state={state} rows={12}>
      {(d) => (
        <div>
          <Header d={d} />
          <Tabs views={VIEWS} />
          {view === 'overview' && <Overview d={d} />}
          {view === 'decisions' && <Decisions run={run} live={live} />}
          {view === 'actions' && <Actions run={run} live={live} />}
          {view === 'snapshots' && <Snapshots run={run} live={live} />}
          {view === 'entities' && <Entities d={d} />}
          {view === 'countries' && <RunCountries run={run} />}
          {view === 'trade' && <RunTrade run={run} />}
        </div>
      )}
    </Loading>
  )
}
