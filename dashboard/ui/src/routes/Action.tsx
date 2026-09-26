import { Link, useParams } from 'react-router-dom'
import { ActionTable, Params } from '@/components/ActionTable'
import { ChangedTables } from '@/components/Changes'
import { Card, KV, Loading, Section, StatusChip } from '@/components/primitives'
import { useApi, type S } from '@/lib/api'
import { label, ms, STATUS_HELP, when } from '@/lib/format'

function Changes({ run, seq }: { run: number; seq: number }) {
  const state = useApi<S['SnapshotChanges']>(`/api/runs/${run}/snapshots/${seq}`)
  return (
    <Loading state={state} rows={8}>
      {(d) => (
        <Section title="what changed by the next snapshot" scope={d.scope}>
          <ChangedTables run={run} seq={seq} tables={d.tables} />
        </Section>
      )}
    </Loading>
  )
}

export function Action() {
  const params = useParams()
  const run = Number(params.run)
  const nth = Number(params.n)
  const state = useApi<S['ActionDetail']>(`/api/runs/${run}/actions/${nth}`)
  return (
    <Loading state={state} rows={10}>
      {(d) => {
        const a = d.action
        return (
          <div className="space-y-8">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <Link className="linka text-sm" to={`/runs/${run}?view=actions`}>
                run {run}
              </Link>
              <h1 className="text-xl font-semibold tracking-tight">
                action {a.n}: {label(a.action)}
              </h1>
              <StatusChip status={a.status} />
              <Link className="linka text-xs" to={`/actions/${a.action}?scope=run:${run}`}>
                every {label(a.action)} in this run
              </Link>
              <span className="ml-auto flex gap-3 text-xs">
                {a.n > 1 && (
                  <Link className="linka" to={`/runs/${run}/actions/${a.n - 1}`}>
                    ← action {a.n - 1}
                  </Link>
                )}
                <Link className="linka" to={`/runs/${run}/actions/${a.n + 1}`}>
                  action {a.n + 1} →
                </Link>
              </span>
            </div>
            <Card className="grid gap-x-10 gap-y-2 px-4 py-3 md:grid-cols-2">
              <KV
                items={[
                  ['group', a.group],
                  ['chosen by', a.advisor],
                  ['turn', String(a.turn)],
                  ['parameters', <Params key="p" row={a} />],
                ]}
              />
              <KV
                items={[
                  ['outcome', <span key="o">{STATUS_HELP[a.status]}</span>],
                  ['executor time', ms(a.ms)],
                  ['chosen from', <Link key="b" className="linka" to={`/runs/${run}/snapshots/${a.before_seq}`}>snapshot {a.before_seq} · {d.before.game_date.text}</Link>],
                  ['checked at', a.after_seq === null ? <span key="n" className="text-dim">no after-snapshot; it never reached the game</span> : <Link key="a" className="linka" to={`/runs/${run}/snapshots/${a.after_seq}`}>snapshot {a.after_seq} · {d.after?.game_date.text}</Link>],
                ]}
              />
              {a.detail && (
                <div className="md:col-span-2">
                  <div className="text-dim text-2xs">detail</div>
                  <code className="text-xs break-words whitespace-pre-wrap">{a.detail}</code>
                </div>
              )}
              <div className="text-dim text-2xs md:col-span-2">logged {when(a.logged_at)}</div>
            </Card>
            <p className="text-sm">
              <Link className="linka" to={`/runs/${run}/blocks/${a.before_seq}`}>
                open the whole block this action belongs to
              </Link>
            </p>
            <Section title="the rest of its batch" scope={{ text: `other actions chosen from snapshot ${a.before_seq}`, detail: 'a batch runs together before the next snapshot, so the changes below belong to the whole batch' }}>
              <ActionTable rows={d.batch} empty="it ran alone" />
            </Section>
            {a.after_seq !== null && <Changes run={run} seq={a.after_seq} />}
          </div>
        )
      }}
    </Loading>
  )
}
