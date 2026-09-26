import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Card, CellView, ErrorState, Pager } from '@/components/primitives'
import { qs, useApi, type S } from '@/lib/api'
import { cn, label, n } from '@/lib/format'

const LIMIT = 100

function ChangeLine({ run, table, row }: { run: number; table: S['TableChanges']; row: S['ChangeRow'] }) {
  const index = Object.fromEntries(table.columns.map((c, i) => [c.name, i]))
  return (
    <tr className="border-line/60 border-b last:border-0">
      <td className="w-px px-3 py-1.5 align-top whitespace-nowrap">
        <span className="flex flex-wrap gap-2">
          {row.keys.map((k, i) => (
            <span key={i}>
              <span className="text-dim text-2xs">{table.keys[i].name} </span>
              <CellView run={run} cell={k} />
            </span>
          ))}
          {!row.keys.length && <span className="text-dim">the player</span>}
        </span>
      </td>
      <td className="w-px px-3 py-1.5 align-top">
        {!row.present ? (
          <span className="bg-bad-soft rounded px-1.5 text-2xs">gone</span>
        ) : row.before === null ? (
          <span className="bg-ok-soft rounded px-1.5 text-2xs">new</span>
        ) : (
          <span className="bg-raised rounded px-1.5 text-2xs">changed</span>
        )}
      </td>
      <td className="px-3 py-1.5 align-top">
        <span className="flex flex-wrap gap-x-4 gap-y-1">
          {(row.present ? row.changed : Object.keys(index)).map((name) => {
            const i = index[name]
            if (!row.present && !row.before) return null
            if (row.before === null)
              return (
                <span key={name} className="whitespace-nowrap">
                  <span className="text-dim">{label(name)}</span> <CellView run={run} cell={row.cells[i]} />
                </span>
              )
            return (
              <span key={name} className="whitespace-nowrap">
                <span className="text-dim">{label(name)}</span> <CellView run={run} cell={row.before[i]} />
                {row.present && (
                  <>
                    <span className="text-dim mx-1">→</span>
                    <CellView run={run} cell={row.cells[i]} />
                  </>
                )}
              </span>
            )
          })}
          {row.present && !row.changed.length && <span className="text-dim text-2xs">keys only</span>}
        </span>
      </td>
    </tr>
  )
}

function TableRows({ run, seq, table }: { run: number; seq: number; table: string }) {
  const [offset, setOffset] = useState(0)
  const state = useApi<S['TableChanges']>(`/api/runs/${run}/snapshots/${seq}/tables/${table}${qs({ offset, limit: LIMIT })}`)
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />
  if (!state.data) return <div className="text-dim px-3 py-3 text-2xs">loading…</div>
  const d = state.data
  return (
    <div className={cn(state.stale && 'stale')}>
      {d.total > LIMIT && (
        <div className="flex justify-end px-3 py-1.5">
          <Pager offset={offset} limit={LIMIT} shown={d.rows.length} total={d.total} onOffset={setOffset} />
        </div>
      )}
      <div className="tablewrap">
        <table className="w-full border-collapse text-xs">
          <tbody>
            {d.rows.map((r, i) => (
              <ChangeLine key={i} run={run} table={d} row={r} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ChangedTables({ run, seq, tables }: { run: number; seq: number; tables: S['TableCount'][] }) {
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [filter, setFilter] = useState('')
  const shown = tables.filter((t) => !filter || t.table.includes(filter) || (t.owner ?? '').includes(filter))
  const toggle = (name: string) => {
    const next = new Set(open)
    next.has(name) ? next.delete(name) : next.add(name)
    setOpen(next)
  }
  return (
    <div className="space-y-2">
      <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="filter tables…" className="border-line w-full max-w-sm rounded-md border px-2 py-1 text-xs" />
      <Card className="divide-line divide-y overflow-hidden">
        {shown.map((t) => (
          <div key={t.table}>
            <button className="hover:bg-raised flex w-full items-center gap-2 px-3 py-2 text-left text-xs" onClick={() => toggle(t.table)}>
              {open.has(t.table) ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
              <code className="font-medium">{t.table}</code>
              <span className="text-dim text-2xs">
                {t.kind}
                {t.owner ? ` of ${label(t.owner)}` : ''}
              </span>
              <span className="num ml-auto">{n(t.rows)} rows</span>
            </button>
            {open.has(t.table) && (
              <div className="bg-bg border-line border-t">
                <TableRows run={run} seq={seq} table={t.table} />
              </div>
            )}
          </div>
        ))}
        {!shown.length && <div className="text-dim px-3 py-6 text-center text-xs">no table matches</div>}
      </Card>
    </div>
  )
}
