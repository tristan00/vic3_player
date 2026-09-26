import { Link, useNavigate, useParams } from 'react-router-dom'
import { ActionTable } from '@/components/ActionTable'
import { StatusBar, StatusLegend } from '@/components/charts'
import { Card, CountText, KV, Loading, Section, StatusChip } from '@/components/primitives'
import { ScopePicker, useScope } from '@/components/ScopePicker'
import { Table, type Col } from '@/components/Table'
import { useApi, type S } from '@/lib/api'
import { label, n } from '@/lib/format'

export function ActionType() {
  const name = useParams().name!
  const scope = useScope()
  const navigate = useNavigate()
  const state = useApi<S['ActionType']>(`/api/actions/${name}?scope=${scope}`, { live: scope !== 'all' })
  const detailCols: Col<S['DetailCount']>[] = [
    { key: 'status', label: 'status', value: (r) => r.status, render: (r) => <StatusChip status={r.status} /> },
    { key: 'detail', label: 'detail', value: (r) => r.detail ?? '', render: (r) => <code className="text-2xs break-words whitespace-pre-wrap">{r.detail ?? '—'}</code> },
    { key: 'count', label: 'times', align: 'right', value: (r) => r.count, render: (r) => n(r.count) },
  ]
  const runCols: Col<S['RunStatus']>[] = [
    { key: 'run', label: 'run', align: 'right', value: (r) => r.run_id, render: (r) => <Link className="linka" to={`/runs/${r.run_id}?view=actions&action=${name}`} onClick={(e) => e.stopPropagation()}>{r.run_id}</Link> },
    { key: 'tag', label: 'country', value: (r) => r.tag, render: (r) => <span className="num">{r.tag}</span> },
    { key: 'total', label: 'picks', align: 'right', value: (r) => r.total, render: (r) => n(r.total) },
    { key: 'mix', label: 'outcomes', render: (r) => <div className="w-56 pt-1"><StatusBar counts={r.statuses} /></div> },
  ]
  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link className="linka text-sm" to={`/actions?scope=${scope}`}>
            actions
          </Link>
          <h1 className="text-xl font-semibold tracking-tight">{label(name)}</h1>
        </div>
        <ScopePicker />
      </div>
      <Loading state={state} rows={12}>
        {(d) => (
          <div className="space-y-8">
            <Card className="grid gap-x-10 gap-y-2 px-4 py-3 md:grid-cols-2">
              <KV
                items={[
                  ['group', d.group],
                  ['random advisor weight', d.weight === 0 ? 'never picked (weight 0)' : String(d.weight)],
                ]}
              />
              <KV items={[['parameters', d.params.length ? d.params.map((p) => `${p.name}: ${p.kind}`).join(', ') : 'none']]} />
            </Card>
            <Section title="outcomes" scope={d.scope}>
              <div className="mb-3">
                <Card className="inline-block px-3 py-1.5">
                  <CountText count={d.total} />
                </Card>
              </div>
              <Card className="space-y-3 px-4 py-3">
                <StatusBar counts={d.statuses} height={14} />
                <StatusLegend counts={d.statuses} />
              </Card>
            </Section>
            <Section title="why it did not go through" scope={{ text: 'the executor detail of every pick that was not done, most common first', detail: 'up to 25 distinct details' }}>
              <Table rows={d.details} cols={detailCols} rowKey={(r, i) => `${r.status}.${i}`} empty="every pick went through" />
            </Section>
            <Section title="per run" scope={{ text: 'runs in this scope that picked it, newest first', detail: 'up to 50' }}>
              <Table rows={d.runs} cols={runCols} rowKey={(r) => String(r.run_id)} onRow={(r) => navigate(`/runs/${r.run_id}?view=actions&action=${name}`)} empty="no run picked it" />
            </Section>
            <Section title="latest picks" scope={{ text: 'the newest picks in this scope', detail: 'up to 50' }}>
              <ActionTable rows={d.recent} showRun empty="no pick in this scope" />
            </Section>
          </div>
        )}
      </Loading>
    </div>
  )
}
