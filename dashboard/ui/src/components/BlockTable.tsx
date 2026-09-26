import { useNavigate } from 'react-router-dom'
import { StatusBar } from '@/components/charts'
import { Table, type Col } from '@/components/Table'
import type { S } from '@/lib/api'
import { cn, label, ms, n } from '@/lib/format'

type Block = S['BlockRow']

const KIND_STYLE: Record<Block['kind'], string> = { decision: 'bg-accent-soft', events: 'bg-warn-soft', time: 'bg-raised' }

export function KindChip({ kind }: { kind: Block['kind'] }) {
  return <span className={cn('rounded-full px-2 py-0.5 text-2xs font-medium whitespace-nowrap', KIND_STYLE[kind])}>{kind}</span>
}

export function BlockActions({ names }: { names: string[] }) {
  const counts = new Map<string, number>()
  names.forEach((name) => counts.set(name, (counts.get(name) ?? 0) + 1))
  return (
    <span className="flex flex-wrap gap-1">
      {[...counts.entries()].map(([name, count]) => (
        <span key={name} className="bg-raised rounded px-1.5 py-0.5 text-2xs whitespace-nowrap">
          {label(name)}
          {count > 1 && <span className="text-dim"> ×{count}</span>}
        </span>
      ))}
    </span>
  )
}

export function BlockTable({ run, rows, empty }: { run: number; rows: Block[]; empty?: string }) {
  const navigate = useNavigate()
  const cols: Col<Block>[] = [
    { key: 'seq', label: 'from snapshot', align: 'right', value: (b) => b.before_seq, render: (b) => <span className="text-dim">{b.before_seq}</span> },
    { key: 'turn', label: 'turn', align: 'right', value: (b) => b.turn, render: (b) => b.turn },
    { key: 'date', label: 'game date', value: (b) => b.game_date.hours, render: (b) => <span className="num text-dim">{b.game_date.text}</span> },
    { key: 'kind', label: 'kind', value: (b) => b.kind, render: (b) => <KindChip kind={b.kind} /> },
    { key: 'count', label: 'actions', align: 'right', value: (b) => b.actions, render: (b) => n(b.actions) },
    { key: 'names', label: 'what it did', render: (b) => <BlockActions names={b.names} /> },
    { key: 'mix', label: 'outcomes', render: (b) => <div className="w-32 pt-1"><StatusBar counts={b.statuses} /></div> },
    { key: 'ms', label: 'executor time', align: 'right', value: (b) => b.ms, render: (b) => ms(b.ms) },
  ]
  return <Table rows={rows} cols={cols} rowKey={(b) => String(b.before_seq)} onRow={(b) => navigate(`/runs/${run}/blocks/${b.before_seq}`)} empty={empty ?? 'no block yet'} />
}
