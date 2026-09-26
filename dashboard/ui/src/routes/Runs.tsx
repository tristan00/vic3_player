import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Card, CountText, EndChip, Loading, Pager, Section, Select, StateChip, Tabs, useTab } from '@/components/primitives'
import { Table, type Col, type SortState } from '@/components/Table'
import { qs, useApi, type RunRow, type S } from '@/lib/api'
import { ago, compact, duration, gameYears, n, when } from '@/lib/format'

const VIEWS = [
  { key: 'runs', label: 'runs', title: 'every recorded run' },
  { key: 'rounds', label: 'rounds', title: 'launches of the loop and the runs each produced' },
]
const LIMIT = 50

function Growth({ value }: { value: number | null }) {
  if (value === null) return <span className="text-muted" title="the run covers less than a game year">—</span>
  return <span className={value < 0 ? 'text-invalid' : ''}>{`${value >= 0 ? '+' : ''}${(100 * value).toFixed(1)}%`}</span>
}

function EndCell({ r }: { r: RunRow }) {
  if (r.state !== 'ended') return <StateChip state={r.state} />
  return <span title={r.end_detail ?? undefined}><EndChip reason={r.end_reason} /></span>
}

function RunsView() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const get = (k: string) => params.get(k) ?? ''
  const offset = Number(get('offset') || 0)
  const sort: SortState = { key: get('sort') || 'run_id', desc: get('asc') !== '1' }
  const set = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) v ? next.set(k, v) : next.delete(k)
    if (!('offset' in changes)) next.delete('offset')
    setParams(next, { replace: true })
  }
  const state = useApi<S['RunsPage']>(
    `/api/runs${qs({ offset, limit: LIMIT, sort: sort.key, desc: sort.desc, kind: get('kind'), end_reason: get('end_reason'), tag: get('tag'), round: get('round') })}`,
    { live: true },
  )
  const cols: Col<RunRow>[] = [
    { key: 'run_id', label: 'run', align: 'right', render: (r) => <Link className="linka" to={`/runs/${r.run_id}`}>{r.run_id}</Link> },
    { key: 'end_reason', label: 'end', render: (r) => <EndCell r={r} /> },
    { key: 'tag', label: 'country', render: (r) => <span className="num">{r.tag}</span> },
    { key: 'started_at', label: 'started', render: (r) => <span title={r.started_at}>{when(r.started_at)}</span> },
    { key: 'wall', label: 'wall time', align: 'right', render: (r) => <span title={`budget ${duration(r.minutes * 60)}`}>{duration(r.wall_s)}</span> },
    {
      key: 'game',
      label: 'game time',
      align: 'right',
      render: (r) => (r.game_from && r.game_to ? <span title={`${r.game_from.text} → ${r.game_to.text}`}>{gameYears(r.game_to.hours - r.game_from.hours)}</span> : '—'),
    },
    { key: 'gdp_start', label: 'gdp start', align: 'right', render: (r) => compact(r.gdp_start) },
    { key: 'gdp_end', label: 'gdp latest', align: 'right', render: (r) => compact(r.gdp_end) },
    {
      key: 'gdp_change',
      label: 'gdp change',
      align: 'right',
      render: (r) => (r.gdp_start && r.gdp_end !== null ? `${r.gdp_end >= r.gdp_start ? '+' : ''}${((100 * (r.gdp_end - r.gdp_start)) / r.gdp_start).toFixed(0)}%` : '—'),
    },
    { key: 'gdp_peak', label: 'gdp peak', align: 'right', render: (r) => compact(r.gdp_peak) },
    { key: 'gdp_yoy', label: 'median y/y gdp', align: 'right', title: 'median of each value against the value one game year earlier', render: (r) => <Growth value={r.gdp_yoy} /> },
    { key: 'population_yoy', label: 'median y/y pop', align: 'right', title: 'median of each value against the value one game year earlier', render: (r) => <Growth value={r.population_yoy} /> },
    { key: 'snapshots', label: 'snapshots', align: 'right', render: (r) => n(r.snapshots) },
    { key: 'actions', label: 'actions', align: 'right', render: (r) => n(r.actions) },
  ]
  const sortable = new Set(['run_id', 'started_at', 'wall', 'end_reason', 'tag'])
  return (
    <Loading state={state} rows={12}>
      {(d) => (
        <Section title="runs" scope={d.scope}>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Card className="px-3 py-1.5">
              <CountText count={d.total} />
            </Card>
            <Select value={get('kind')} onChange={(v) => set({ kind: v })} all="every world kind" options={d.kinds.map((f) => ({ value: f.value, label: `${f.value} · ${f.count}` }))} />
            <Select value={get('end_reason')} onChange={(v) => set({ end_reason: v })} all="every ending" options={d.end_reasons.map((f) => ({ value: f.value, label: `${f.value.replaceAll('_', ' ')} · ${f.count}` }))} />
            <Select value={get('tag')} onChange={(v) => set({ tag: v })} all="every country" options={d.tags.map((f) => ({ value: f.value, label: `${f.value} · ${f.count}` }))} />
            {get('round') && (
              <button className="bg-raised rounded-md px-2 py-1 text-xs" onClick={() => set({ round: '' })} title="clear the round filter">
                round <span className="num">{get('round')}</span> ✕
              </button>
            )}
            <div className="ml-auto">
              <Pager offset={offset} limit={LIMIT} shown={d.rows.length} total={d.total.value} onOffset={(o) => set({ offset: String(o) })} />
            </div>
          </div>
          <Table
            rows={d.rows}
            cols={cols.map((c) => ({ ...c, sortable: sortable.has(c.key) }))}
            rowKey={(r) => String(r.run_id)}
            onRow={(r) => navigate(`/runs/${r.run_id}`)}
            sort={sort}
            onSort={(s) => (s ? set({ sort: s.key === 'run_id' ? '' : s.key, asc: s.desc ? '' : '1' }) : set({ sort: '', asc: '' }))}
            empty="no run matches these filters"
            why="clear a filter, or start a round"
          />
        </Section>
      )}
    </Loading>
  )
}

function RoundsView() {
  const [params, setParams] = useSearchParams()
  const offset = Number(params.get('offset') ?? 0)
  const state = useApi<S['RoundsPage']>(`/api/rounds${qs({ offset, limit: LIMIT })}`, { live: true })
  const cols: Col<S['RoundRow']>[] = [
    { key: 'round', label: 'round', value: (r) => r.round, render: (r) => <Link className="linka num" to={`/runs?round=${r.round}`}>{r.round}</Link> },
    { key: 'started', label: 'started', value: (r) => r.started_at, render: (r) => <span title={r.started_at}>{when(r.started_at)}</span> },
    { key: 'last', label: 'last activity', value: (r) => r.last_at, render: (r) => ago(r.last_at) },
    { key: 'runs', label: 'runs', align: 'right', value: (r) => r.runs, render: (r) => <span>{n(r.runs)}{r.live ? <span className="text-dim"> · {r.live} open</span> : null}</span> },
    { key: 'kinds', label: 'worlds', render: (r) => r.kinds.map((k) => `${k.value} ${k.count}`).join(', ') },
    {
      key: 'ends',
      label: 'endings',
      render: (r) => (
        <span className="flex flex-wrap gap-1.5">
          {r.end_reasons.map((e) => (
            <span key={e.value} className="inline-flex items-center gap-1">
              {e.value === 'open' ? <span className="text-dim text-2xs">open</span> : <EndChip reason={e.value} />}
              <span className="num text-2xs">{e.count}</span>
            </span>
          ))}
        </span>
      ),
    },
    { key: 'tags', label: 'countries', render: (r) => <span className="num text-2xs" title={r.tags.join(' ')}>{r.tags.slice(0, 12).join(' ')}{r.tags.length > 12 ? ` +${r.tags.length - 12}` : ''}</span> },
    { key: 'actions', label: '', render: (r) => <Link className="linka text-2xs" to={`/actions?scope=round:${r.round}`}>actions</Link> },
  ]
  return (
    <Loading state={state} rows={10}>
      {(d) => (
        <Section
          title="rounds"
          scope={d.scope}
          right={<Pager offset={offset} limit={LIMIT} shown={d.rows.length} total={d.total.value} onOffset={(o) => setParams({ view: 'rounds', offset: String(o) })} />}
        >
          <Table rows={d.rows} cols={cols} rowKey={(r) => String(r.round)} empty="no round recorded" />
        </Section>
      )}
    </Loading>
  )
}

export function Runs() {
  const view = useTab(VIEWS)
  return (
    <div>
      <Tabs views={VIEWS} />
      {view === 'rounds' ? <RoundsView /> : <RunsView />}
    </div>
  )
}
