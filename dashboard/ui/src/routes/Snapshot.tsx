import { Link, useParams } from 'react-router-dom'
import { ActionTable } from '@/components/ActionTable'
import { ChangedTables } from '@/components/Changes'
import { Card, KV, Loading, Section } from '@/components/primitives'
import { useApi, type S } from '@/lib/api'
import { duration, ms, n, when } from '@/lib/format'

export function Snapshot() {
  const params = useParams()
  const run = Number(params.run)
  const seq = Number(params.seq)
  const state = useApi<S['SnapshotChanges']>(`/api/runs/${run}/snapshots/${seq}`)
  return (
    <Loading state={state} rows={12}>
      {(d) => {
        const s = d.snapshot
        const gap = d.previous ? (Date.parse(s.taken_at) - Date.parse(d.previous.taken_at)) / 1000 : null
        const gameGap = d.previous ? s.game_date.hours - d.previous.game_date.hours : null
        return (
          <div className="space-y-8">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <Link className="linka text-sm" to={`/runs/${run}?view=snapshots`}>
                run {run}
              </Link>
              <h1 className="text-xl font-semibold tracking-tight">snapshot {s.seq}</h1>
              <span className="bg-raised rounded-full px-2 py-0.5 text-2xs">{s.phase.replaceAll('_', ' ')}</span>
              <span className="ml-auto flex gap-3 text-xs">
                {seq > 0 && (
                  <Link className="linka" to={`/runs/${run}/snapshots/${seq - 1}`}>
                    ← snapshot {seq - 1}
                  </Link>
                )}
                <Link className="linka" to={`/runs/${run}/snapshots/${seq + 1}`}>
                  snapshot {seq + 1} →
                </Link>
              </span>
            </div>
            <Card className="grid gap-x-10 gap-y-2 px-4 py-3 md:grid-cols-2">
              <KV
                items={[
                  ['game date', <span key="d" className="num">{s.game_date.text}</span>],
                  ['game time since the previous', gameGap === null ? '—' : `${n(gameGap / 24, 1)} days`],
                  ['taken', when(s.taken_at)],
                  ['wall time since the previous', gap === null ? '—' : duration(gap)],
                ]}
              />
              <KV
                items={[
                  ['read took', ms(s.read_ms)],
                  ['clock', s.paused === null ? 'unread' : s.paused ? 'paused' : `speed ${s.speed}`],
                  ['open windows', [s.ui_panel_open && 'panel', s.ui_interaction_open && 'interaction', s.ui_map_list_open && 'map list'].filter(Boolean).join(', ') || 'none'],
                  ['tables with changes', n(d.tables.length)],
                ]}
              />
            </Card>
            <Section title="actions that ended here" scope={{ text: `actions whose after-snapshot is ${s.seq}`, detail: 'they ran between the previous snapshot and this one' }}>
              <ActionTable rows={d.actions} empty="no action ended at this snapshot" why="failed actions have no after-snapshot; the start snapshot of a run has none either" />
            </Section>
            <Section title="what changed" scope={d.scope}>
              <ChangedTables run={run} seq={seq} tables={d.tables} />
            </Section>
          </div>
        )
      }}
    </Loading>
  )
}
