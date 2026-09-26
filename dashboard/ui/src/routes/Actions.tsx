import { Link, useNavigate } from 'react-router-dom'
import { StatusBar, StatusLegend } from '@/components/charts'
import { Card, CountText, Loading, Section, statusTotal } from '@/components/primitives'
import { ScopePicker, useScope } from '@/components/ScopePicker'
import { Table, type Col } from '@/components/Table'
import { useApi, type S } from '@/lib/api'
import { label, ms, n, STATUS_LABEL, STATUSES } from '@/lib/format'

function share(row: { statuses: S['StatusCount'][]; total: number }, status: string) {
  const c = row.statuses.find((s) => s.status === status)!.count
  return row.total ? c / row.total : 0
}

export function Actions() {
  const scope = useScope()
  const navigate = useNavigate()
  const state = useApi<S['ActionStats']>(`/api/actions?scope=${scope}`, { live: scope !== 'all' })
  const cols: Col<S['ActionStat']>[] = [
    { key: 'action', label: 'action', value: (r) => r.action, render: (r) => <Link className="linka" to={`/actions/${r.action}?scope=${scope}`}>{label(r.action)}</Link> },
    { key: 'group', label: 'group', value: (r) => r.group, render: (r) => <span className="text-dim">{r.group}</span> },
    { key: 'total', label: 'picks', align: 'right', value: (r) => r.total, render: (r) => n(r.total) },
    { key: 'runs', label: 'runs', align: 'right', value: (r) => r.runs, render: (r) => n(r.runs) },
    { key: 'mix', label: 'outcomes', render: (r) => <div className="w-44 pt-1"><StatusBar counts={r.statuses} /></div> },
    ...STATUSES.map((s) => ({
      key: s,
      label: STATUS_LABEL[s],
      align: 'right' as const,
      value: (r: S['ActionStat']) => share(r, s),
      render: (r: S['ActionStat']) => {
        const p = share(r, s)
        return p ? `${(100 * p).toFixed(p < 0.1 ? 1 : 0)}%` : <span className="text-muted">·</span>
      },
    })),
    { key: 'median', label: 'median ms', align: 'right', value: (r) => r.ms_median, render: (r) => ms(r.ms_median) },
    { key: 'p90', label: 'p90 ms', align: 'right', value: (r) => r.ms_p90, render: (r) => ms(r.ms_p90) },
  ]
  const groupCols: Col<S['GroupStatus']>[] = [
    { key: 'group', label: 'group', value: (g) => g.group, render: (g) => g.group },
    { key: 'total', label: 'picks', align: 'right', value: (g) => g.total, render: (g) => n(g.total) },
    { key: 'mix', label: 'outcomes', render: (g) => <div className="w-64 pt-1"><StatusBar counts={g.statuses} /></div> },
    { key: 'done', label: 'done', align: 'right', value: (g) => share(g, 'done'), render: (g) => `${(100 * share(g, 'done')).toFixed(0)}%` },
  ]
  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">actions</h1>
        <ScopePicker />
      </div>
      <Loading state={state} rows={14}>
        {(d) => (
          <div className="space-y-8">
            <Section title="outcomes" scope={d.scope}>
              <div className="mb-3 flex flex-wrap gap-2">
                <Card className="px-3 py-1.5">
                  <CountText count={d.total} />
                </Card>
                <Card className="px-3 py-1.5">
                  <CountText count={d.runs} />
                </Card>
              </div>
              <Card className="space-y-3 px-4 py-3">
                <StatusBar counts={d.statuses} height={14} />
                <StatusLegend counts={d.statuses} />
              </Card>
            </Section>
            <Section title="by group" scope={{ text: 'the catalogue groups actions by the part of the game they touch' }}>
              <Table rows={d.groups} cols={groupCols} rowKey={(g) => g.group} empty="no action in this scope" />
            </Section>
            <Section title="by action" scope={{ text: `every action picked in this scope, ${n(d.rows.length)} kinds`, detail: 'shares are of that action’s picks; click a row for its failures and runs' }}>
              <Table rows={d.rows} cols={cols} rowKey={(r) => r.action} onRow={(r) => navigate(`/actions/${r.action}?scope=${scope}`)} empty="no action in this scope" why="pick another scope, or wait for a run to finish" />
            </Section>
            {d.never.length > 0 && (
              <Section title="never picked" scope={{ text: `catalogue actions with no pick in this scope`, detail: `${d.never.length} of them; some carry a weight of zero` }}>
                <Card className="flex flex-wrap gap-x-3 gap-y-1 px-4 py-3 text-xs">
                  {d.never.map((a) => (
                    <Link key={a} className="linka" to={`/actions/${a}?scope=${scope}`}>
                      {label(a)}
                    </Link>
                  ))}
                </Card>
              </Section>
            )}
            <p className="text-dim text-2xs">{n(statusTotal(d.statuses))} actions counted</p>
          </div>
        )}
      </Loading>
    </div>
  )
}
