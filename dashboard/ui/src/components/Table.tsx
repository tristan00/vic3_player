import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { Card, EmptyState } from '@/components/primitives'
import { cn } from '@/lib/format'

export interface Col<T> {
  key: string
  label: ReactNode
  align?: 'left' | 'right'
  title?: string
  sortable?: boolean
  value?: (row: T) => string | number | null | undefined
  render: (row: T) => ReactNode
}

export interface SortState {
  key: string
  desc: boolean
}

export function Table<T>({
  rows,
  cols,
  rowKey,
  onRow,
  empty = 'nothing to show',
  why,
  sort,
  onSort,
  maxHeight,
}: {
  rows: T[]
  cols: Col<T>[]
  rowKey: (row: T, i: number) => string
  onRow?: (row: T) => void
  empty?: string
  why?: string
  sort?: SortState | null
  onSort?: (s: SortState | null) => void
  maxHeight?: number
}) {
  const [local, setLocal] = useState<SortState | null>(null)
  const active = onSort ? sort ?? null : local
  const sorted = useMemo(() => {
    if (onSort || !local) return rows
    const col = cols.find((c) => c.key === local.key)
    if (!col?.value) return rows
    const get = col.value
    return [...rows].sort((a, b) => {
      const x = get(a)
      const y = get(b)
      if (x === y) return 0
      if (x === null || x === undefined) return 1
      if (y === null || y === undefined) return -1
      const c = x < y ? -1 : 1
      return local.desc ? -c : c
    })
  }, [rows, cols, local, onSort])
  if (!rows.length) return <EmptyState what={empty} why={why} />
  const toggle = (key: string) => {
    const next = active?.key === key ? (active.desc ? null : { key, desc: true }) : { key, desc: false }
    if (onSort) onSort(next)
    else setLocal(next)
  }
  return (
    <Card className="overflow-hidden">
      <div className="tablewrap" style={{ maxHeight }}>
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-line border-b">
              {cols.map((c) => {
                const sortable = onSort ? Boolean(c.sortable) : Boolean(c.value)
                const on = active?.key === c.key
                return (
                  <th key={c.key} title={c.title} className={cn('text-dim px-3 py-1.5 font-medium whitespace-nowrap', c.align === 'right' ? 'text-right' : 'text-left')}>
                    {sortable ? (
                      <button type="button" onClick={() => toggle(c.key)} className="hover:text-fg inline-flex items-center gap-1">
                        {c.label}
                        {on ? active!.desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" /> : <ChevronsUpDown className="size-3 opacity-30" />}
                      </button>
                    ) : (
                      c.label
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => (
              <tr
                key={rowKey(r, i)}
                onClick={onRow ? () => onRow(r) : undefined}
                className={cn('border-line/60 border-b last:border-0', onRow && 'hover:bg-raised cursor-pointer')}
              >
                {cols.map((c) => (
                  <td key={c.key} className={cn('px-3 py-1.5 align-top', c.align === 'right' ? 'num text-right' : 'text-left')}>
                    {c.render(r)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
