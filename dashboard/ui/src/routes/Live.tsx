import { Link, useNavigate } from 'react-router-dom'
import { ActionTable } from '@/components/ActionTable'
import { BlockTable } from '@/components/BlockTable'
import { LineChart, StatusBar, StatusLegend } from '@/components/charts'
import { Card, EmptyState, EndChip, Eyebrow, Loading, RateText, RefLink, Section, StateChip, statusTotal, Tile } from '@/components/primitives'
import { useApi, type S } from '@/lib/api'
import { ago, duration, gameYears, HOURS_PER_YEAR, ms, n } from '@/lib/format'

function Meter({ value, of }: { value: number; of: number }) {
  const p = of > 0 ? Math.min(100, (100 * value) / of) : 0
  return (
    <div className="bg-accent-soft mt-2 h-1.5 w-full rounded-full" title={`${p.toFixed(0)}%`}>
      <div className="h-full rounded-full" style={{ width: `${p}%`, background: 'var(--series)' }} />
    </div>
  )
}

function LiveRunCard({ live, blocks }: { live: S['LiveRun']; blocks: S['BlockRow'][] }) {
  const navigate = useNavigate()
  const run = live.run
  const spanHours = live.game_start && live.game_now ? live.game_now.hours - live.game_start.hours : 0
  return (
    <div className="space-y-6">
      <Card className="px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <Link to={`/runs/${run.run_id}`} className="linka text-lg font-semibold">
            run {run.run_id}
          </Link>
          <StateChip state={run.state} />
          <span className="text-sm">
            playing <RefLink run={run.run_id} refd={live.player} /> <span className="text-dim num">{run.tag}</span>
          </span>
          <span className="text-dim text-xs">
            {run.kind} world <span className="num">{run.world}</span> · round{' '}
            <Link className="linka num" to={`/runs?view=runs&round=${run.round}`}>
              {run.round}
            </Link>{' '}
            · advisors {run.advisors.join(', ')}
          </span>
        </div>
        <div className="text-dim mt-2 flex flex-wrap gap-x-5 gap-y-1 text-2xs">
          <span>
            step <code className="text-fg">{live.progress_step}</code> for {duration(live.progress_age_s)}
          </span>
          <span>heartbeat {live.heartbeat_age_s < 1 ? `${ms(live.heartbeat_age_s * 1000)} ago` : `${duration(live.heartbeat_age_s)} ago`}</span>
          <span>started {ago(run.started_at)}</span>
        </div>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Tile label="wall time" value={duration(run.wall_s)} sub={`budget ${duration(run.minutes * 60)}`}>
          <Meter value={run.wall_s} of={run.minutes * 60} />
        </Tile>
        <Tile label="game time" value={gameYears(spanHours)} sub={`${live.game_start?.text ?? '—'} → ${live.game_now?.text ?? '—'} · target ${run.years}y`}>
          <Meter value={spanHours} of={run.years * HOURS_PER_YEAR} />
        </Tile>
        <Tile label="turn" value={n(live.turn)} sub="one turn is a batch of actions, then days of game time" />
        <Tile label="actions" value={n(run.actions)} sub={<RateText rate={run.done} />} />
        <Tile label="snapshots" value={n(run.snapshots)} sub={`median read ${ms(median(live.read_ms))} over the last ${live.read_ms.length}`} />
      </div>

      <Section title="how its actions fared" scope={{ text: `every action run ${run.run_id} logged so far`, detail: `${n(statusTotal(live.statuses))} actions` }}>
        <Card className="space-y-3 px-4 py-3">
          <StatusBar counts={live.statuses} height={14} onPick={(s) => navigate(`/runs/${run.run_id}?view=actions&status=${s}`)} />
          <StatusLegend counts={live.statuses} />
        </Card>
      </Section>

      <Section title="snapshot read time" scope={{ text: `the last ${live.read_ms.length} snapshots of run ${run.run_id}`, detail: 'click a point to open that snapshot' }}>
        <Card className="px-2 py-2">
          <LineChart
            xs={live.read_seq}
            ys={live.read_ms}
            height={140}
            xFormat={(x) => `#${n(x)}`}
            yFormat={(y) => ms(y)}
            tip={(i) => `snapshot ${live.read_seq[i]}`}
            onPick={(i) => navigate(`/runs/${run.run_id}/snapshots/${live.read_seq[i]}`)}
          />
        </Card>
      </Section>

      <Section
        title="latest decisions"
        scope={{ text: `the last ${blocks.length} decision blocks of run ${run.run_id}, newest first`, detail: 'a block is every action the advisor chose from one snapshot' }}
        right={
          <Link className="linka text-xs" to={`/runs/${run.run_id}?view=decisions`}>
            every block of this run
          </Link>
        }
      >
        <BlockTable run={run.run_id} rows={blocks} empty="no decision yet" />
      </Section>

      <Section
        title="latest actions"
        scope={{ text: `the last ${live.recent.length} actions of run ${run.run_id}, newest first` }}
        right={
          <Link className="linka text-xs" to={`/runs/${run.run_id}?view=actions`}>
            every action of this run
          </Link>
        }
      >
        <ActionTable rows={live.recent} />
      </Section>
    </div>
  )
}

function median(values: number[]): number | null {
  if (!values.length) return null
  const s = [...values].sort((a, b) => a - b)
  return s[Math.floor(s.length / 2)]
}

function RoundCard({ round }: { round: S['RoundRow'] }) {
  return (
    <Card className="px-5 py-4">
      <Eyebrow>latest round</Eyebrow>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-5 gap-y-1">
        <Link className="linka num text-base font-semibold" to={`/runs?view=runs&round=${round.round}`}>
          {round.round}
        </Link>
        <span>
          <b className="num">{n(round.runs)}</b> runs{round.live ? `, ${round.live} open` : ''}
        </span>
        <span>
          <b className="num">{n(round.actions)}</b> actions
        </span>
        <span className="text-dim text-xs">started {ago(round.started_at)}</span>
        <span className="flex flex-wrap gap-1.5">
          {round.end_reasons.map((e) => (
            <span key={e.value} className="inline-flex items-center gap-1">
              {e.value === 'open' ? <span className="text-dim text-2xs">open</span> : <EndChip reason={e.value} />}
              <span className="num text-2xs">{e.count}</span>
            </span>
          ))}
        </span>
        <Link className="linka ml-auto text-xs" to={`/actions?scope=round:${round.round}`}>
          actions of this round
        </Link>
      </div>
    </Card>
  )
}

export function Live() {
  const state = useApi<S['LivePage']>('/api/live', { live: true })
  return (
    <Loading state={state} rows={10}>
      {(d) => (
        <div className="space-y-8">
          {d.round && <RoundCard round={d.round} />}
          {d.live.map((l) => (
            <LiveRunCard key={l.run.run_id} live={l} blocks={d.blocks[l.run.run_id] ?? []} />
          ))}
          {!d.live.length && (
            <div className="space-y-4">
              <EmptyState what="no run is open right now" why="the loop is not recording; this page updates on its own when a run starts" />
              {d.last && (
                <Card className="flex flex-wrap items-center gap-4 px-5 py-4">
                  <Eyebrow>last run</Eyebrow>
                  <Link className="linka font-semibold" to={`/runs/${d.last.run_id}`}>
                    run {d.last.run_id}
                  </Link>
                  <span className="num">{d.last.tag}</span>
                  <EndChip reason={d.last.end_reason} />
                  <span className="text-dim text-xs">
                    ended {ago(d.last.ended_at)} after {duration(d.last.wall_s)} · {n(d.last.actions)} actions
                  </span>
                </Card>
              )}
            </div>
          )}
        </div>
      )}
    </Loading>
  )
}
