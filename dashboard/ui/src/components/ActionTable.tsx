import { Link, useNavigate } from 'react-router-dom'
import { RefLink, StatusChip } from '@/components/primitives'
import { Table, type Col } from '@/components/Table'
import type { ActionRow } from '@/lib/api'
import { label, ms, n } from '@/lib/format'

export function Params({ row }: { row: ActionRow }) {
  if (!row.params.length) return <span className="text-muted">—</span>
  return (
    <span className="flex flex-wrap gap-x-2.5 gap-y-0.5">
      {row.params.map((p) => (
        <span key={p.name} className="whitespace-nowrap">
          <span className="text-dim">{p.name}</span> {p.ref ? <RefLink run={row.run_id} refd={p.ref} /> : <span className="num">{p.text}</span>}
        </span>
      ))}
    </span>
  )
}

export function ActionTable({ rows, showRun = false, empty, why }: { rows: ActionRow[]; showRun?: boolean; empty?: string; why?: string }) {
  const navigate = useNavigate()
  const cols: Col<ActionRow>[] = [
    ...(showRun
      ? [
          {
            key: 'run',
            label: 'run',
            align: 'right' as const,
            value: (r: ActionRow) => r.run_id,
            render: (r: ActionRow) => (
              <Link className="linka" to={`/runs/${r.run_id}`} onClick={(e) => e.stopPropagation()}>
                {r.run_id}
              </Link>
            ),
          },
        ]
      : []),
    { key: 'n', label: '#', align: 'right', value: (r) => r.n, render: (r) => <span className="text-dim">{n(r.n)}</span> },
    { key: 'turn', label: 'turn', align: 'right', value: (r) => r.turn, render: (r) => r.turn },
    { key: 'date', label: 'game date', value: (r) => r.game_date.hours, render: (r) => <span className="num text-dim">{r.game_date.text}</span> },
    {
      key: 'action',
      label: 'action',
      value: (r) => r.action,
      render: (r) => (
        <Link className="linka whitespace-nowrap" to={`/actions/${r.action}?scope=run:${r.run_id}`} onClick={(e) => e.stopPropagation()}>
          {label(r.action)}
        </Link>
      ),
    },
    { key: 'group', label: 'group', value: (r) => r.group, render: (r) => <span className="text-dim">{r.group}</span> },
    { key: 'params', label: 'parameters', render: (r) => <Params row={r} /> },
    { key: 'status', label: 'status', value: (r) => r.status, render: (r) => <StatusChip status={r.status} /> },
    { key: 'detail', label: 'detail', value: (r) => r.detail ?? '', render: (r) => <span className="text-dim line-clamp-2 max-w-[420px] text-2xs">{r.detail ?? ''}</span> },
    { key: 'ms', label: 'ms', align: 'right', value: (r) => r.ms ?? -1, render: (r) => ms(r.ms) },
  ]
  return (
    <Table
      rows={rows}
      cols={cols}
      rowKey={(r) => `${r.run_id}.${r.n}`}
      onRow={(r) => navigate(`/runs/${r.run_id}/actions/${r.n}`)}
      empty={empty ?? 'no action logged'}
      why={why}
    />
  )
}
