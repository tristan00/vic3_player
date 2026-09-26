import { Link, useParams } from 'react-router-dom'
import { ActionTable } from '@/components/ActionTable'
import { KindChip } from '@/components/BlockTable'
import { ChangedTables } from '@/components/Changes'
import { StatusBar, StatusLegend } from '@/components/charts'
import { Card, KV, Loading, Section } from '@/components/primitives'
import { useApi, type S } from '@/lib/api'
import { duration, ms, n } from '@/lib/format'

function Changes({ run, seq }: { run: number; seq: number }) {
  const state = useApi<S['SnapshotChanges']>(`/api/runs/${run}/snapshots/${seq}`)
  return (
    <Loading state={state} rows={8}>
      {(d) => (
        <Section title="what the block changed by the next snapshot" scope={d.scope}>
          <ChangedTables run={run} seq={seq} tables={d.tables} />
        </Section>
      )}
    </Loading>
  )
}

export function Block() {
  const params = useParams()
  const run = Number(params.run)
  const seq = Number(params.seq)
  const state = useApi<S['BlockDetail']>(`/api/runs/${run}/blocks/${seq}`)
  return (
    <Loading state={state} rows={12}>
      {(d) => {
        const b = d.block
        const wall = d.after ? (Date.parse(d.after.taken_at) - Date.parse(d.before.taken_at)) / 1000 : null
        return (
          <div className="space-y-8">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <Link className="linka text-sm" to={`/runs/${run}?view=decisions`}>
                run {run}
              </Link>
              <h1 className="text-xl font-semibold tracking-tight">block at snapshot {b.before_seq}</h1>
              <KindChip kind={b.kind} />
              <span className="ml-auto flex gap-3 text-xs">
                {d.previous !== null && (
                  <Link className="linka" to={`/runs/${run}/blocks/${d.previous}`}>
                    ← previous block
                  </Link>
                )}
                {d.next !== null && (
                  <Link className="linka" to={`/runs/${run}/blocks/${d.next}`}>
                    next block →
                  </Link>
                )}
              </span>
            </div>
            <Card className="grid gap-x-10 gap-y-2 px-4 py-3 md:grid-cols-2">
              <KV
                items={[
                  ['turn', String(b.turn)],
                  ['game date', <span key="d" className="num">{b.game_date.text}</span>],
                  ['actions', n(b.actions)],
                  ['executor time', ms(b.ms)],
                ]}
              />
              <KV
                items={[
                  ['chosen from', <Link key="b" className="linka" to={`/runs/${run}/snapshots/${b.before_seq}`}>snapshot {b.before_seq}</Link>],
                  ['checked at', b.after_seq === null ? <span key="n" className="text-dim">no action reached the game</span> : <Link key="a" className="linka" to={`/runs/${run}/snapshots/${b.after_seq}`}>snapshot {b.after_seq}</Link>],
                  ['wall time to the next snapshot', wall === null ? '—' : duration(wall)],
                  ['game time to the next snapshot', d.after ? `${n((d.after.game_date.hours - d.before.game_date.hours) / 24, 1)} days` : '—'],
                ]}
              />
              <div className="space-y-2 md:col-span-2">
                <StatusBar counts={b.statuses} height={12} />
                <StatusLegend counts={b.statuses} />
              </div>
            </Card>
            <Section title="the actions of the block" scope={{ text: `every action chosen from snapshot ${b.before_seq}, in the order they ran` }}>
              <ActionTable rows={d.actions} />
            </Section>
            {b.after_seq !== null && <Changes run={run} seq={b.after_seq} />}
          </div>
        )
      }}
    </Loading>
  )
}
