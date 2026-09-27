import { ArrowDown, ArrowUp, Filter, LineChart as PlotIcon, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Card, ErrorState } from '@/components/primitives'
import { qs, useApi, type Cell, type Grid, type GridColumn } from '@/lib/api'
import { cn, n, num, when } from '@/lib/format'

const LIMITS = [50, 100, 500]

export function useGridState(id: string, limit: number) {
  const [params, setParams] = useSearchParams()
  const key = (k: string) => `${id}.${k}`
  const state = {
    filters: params.getAll(key('f')),
    sort: params.get(key('sort')),
    desc: params.get(key('desc')) === '1',
    offset: Number(params.get(key('offset')) ?? 0),
    limit: Number(params.get(key('limit')) ?? limit),
  }
  const update = (changes: Partial<typeof state>) => {
    const next = new URLSearchParams(params)
    const merged = { ...state, offset: 0, ...changes }
    next.delete(key('f'))
    merged.filters.forEach((f) => next.append(key('f'), f))
    for (const [k, v, empty] of [
      ['sort', merged.sort, null],
      ['desc', merged.desc ? '1' : null, null],
      ['offset', merged.offset ? String(merged.offset) : null, null],
      ['limit', merged.limit !== limit ? String(merged.limit) : null, null],
    ] as const) {
      if (v === empty) next.delete(key(k))
      else next.set(key(k), v)
    }
    setParams(next, { replace: true })
  }
  return { ...state, update }
}

export function cellText(cell: Cell): string {
  if (cell.ref) return cell.ref.label ?? String(cell.ref.id)
  if (cell.text !== null && cell.text !== undefined) return cell.text
  if (cell.num !== null && cell.num !== undefined) return String(cell.num)
  return '∅'
}

function filterValue(cell: Cell): string {
  if (cell.ref) return String(cell.ref.id)
  if (cell.num !== null && cell.num !== undefined) return String(cell.num)
  if (cell.text !== null && cell.text !== undefined) return cell.text
  return '∅'
}

export function href(col: GridColumn, cell: Cell, run: number | null | undefined): string | null {
  const r = cell.ref
  if (r) {
    if (r.kind === 'run') return `/runs/${r.id}`
    if (r.kind === 'snapshot') return `/runs/${r.run}/snapshots/${r.id}`
    if (r.kind === 'action') return `/runs/${r.run}/actions/${r.id}`
    return `/runs/${r.run}/entities/${r.kind}/${r.id}`
  }
  if (cell.text === null || cell.text === undefined) return null
  if (col.kind === 'action') return `/actions/${cell.text}`
  if (col.kind === 'table') return run ? `/runs/${run}/tables/${cell.text}` : `/schema?schema.f=table:${cell.text}`
  if (col.kind === 'kind') return `/runs/${run}/entities/${cell.text}`
  if (col.kind === 'round') return `/?runs.f=round:${cell.text}`
  return null
}

export function CellValue({ col, cell, run, link }: { col: GridColumn; cell: Cell; run?: number | null; link?: string | null }) {
  const to = link === undefined ? href(col, cell, run) : link
  let shown: ReactNode
  if (cell.ref) shown = cell.ref.label ?? cell.ref.id
  else if (col.kind === 'time' && cell.text) shown = when(cell.text)
  else if (cell.text !== null && cell.text !== undefined) shown = cell.text
  else if (cell.num !== null && cell.num !== undefined) shown = num(cell.num)
  else return <span className="text-muted">∅</span>
  const title = cell.ref ? `${cell.ref.kind} ${cell.ref.id}` : cell.num !== null && cell.num !== undefined ? String(cell.num) : undefined
  if (to)
    return (
      <Link to={to} className="linka" title={title} onClick={(e) => e.stopPropagation()}>
        {shown}
      </Link>
    )
  return <span title={title}>{shown}</span>
}

function right(col: GridColumn) {
  return col.kind === 'number' || col.kind === 'seq' || col.kind === 'n' || col.kind === 'run'
}

function groups(cols: GridColumn[]) {
  const out: { group: string | null; span: number }[] = []
  for (const c of cols) {
    const g = c.group ?? null
    if (out.length && out[out.length - 1].group === g) out[out.length - 1].span++
    else out.push({ group: g, span: 1 })
  }
  return out
}

export function GridTable({
  grid,
  sort,
  desc,
  onSort,
  onFilter,
  onRow,
  plottable,
  onPlot,
  link,
  hidden = [],
}: {
  grid: Grid
  hidden?: string[]
  sort?: string | null
  desc?: boolean
  onSort?: (name: string) => void
  onFilter?: (name: string, value: string) => void
  onRow?: (row: Cell[]) => void
  plottable?: boolean
  onPlot?: (column: string) => void
  link?: (col: GridColumn, cell: Cell, row: Cell[]) => string | null | undefined
}) {
  const shown = grid.columns.map((c, i) => ({ c, i })).filter(({ c }) => !hidden.includes(c.name))
  const cols = shown.map(({ c }) => c)
  const grouped = cols.some((c) => c.group)
  const before = new Map(grid.columns.map((c, i) => [c.name, i]))
  if (!grid.rows.length) return <Card className="text-dim w-fit px-3 py-2 text-xs">0 rows</Card>
  const first = (k: number) => k === 0 && 'bg-surface sticky left-0 z-[1]'
  return (
    <Card className="w-fit max-w-full overflow-hidden">
      <div className="tablewrap max-h-[70vh]">
        <table className="border-collapse text-xs">
          <thead className="bg-surface sticky top-0 z-10">
            {grouped && (
              <tr className="border-line border-b">
                {groups(cols).map((g, i) => (
                  <th key={i} colSpan={g.span} className={cn('text-dim px-2 py-1 text-left text-2xs font-medium whitespace-nowrap', i > 0 && 'border-line border-l')}>
                    {g.group ?? ''}
                  </th>
                ))}
              </tr>
            )}
            <tr className="border-line border-b">
              {cols.map((c, k) => (
                <th key={c.name} className={cn('text-dim px-2 py-1 font-medium whitespace-nowrap', right(c) ? 'text-right' : 'text-left', first(k))}>
                  <span className="inline-flex items-center gap-1">
                    {onSort ? (
                      <button type="button" onClick={() => onSort(c.name)} className="hover:text-fg inline-flex items-center gap-0.5">
                        {c.label}
                        {sort === c.name && (desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
                      </button>
                    ) : (
                      c.label
                    )}
                    {plottable && onPlot && c.kind === 'number' && (
                      <button type="button" onClick={() => onPlot(c.name)} className="hover:text-fg opacity-60" aria-label={`plot ${c.name}`}>
                        <PlotIcon className="size-3" />
                      </button>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.rows.map((row, ri) => (
              <tr key={ri} onClick={onRow ? () => onRow(row) : undefined} className={cn('border-line/60 group/row border-b last:border-0', onRow && 'hover:bg-raised cursor-pointer')}>
                {shown.map(({ c: col, i }, k) => {
                  const cell = row[i]
                  const prior = before.get(`${col.name}.before`)
                  const changed = prior !== undefined && cellText(row[prior]) !== cellText(cell)
                  return (
                    <td key={i} className={cn('group/cell px-2 py-1 align-top whitespace-nowrap', right(col) && 'num text-right', changed && 'bg-accent-soft', first(k))}>
                      <span className="inline-flex items-center gap-1">
                        <CellValue col={col} cell={cell} run={grid.run} link={link ? link(col, cell, row) : undefined} />
                        {onFilter && (
                          <button
                            type="button"
                            aria-label={`filter ${col.name}`}
                            onClick={(e) => {
                              e.stopPropagation()
                              onFilter(col.name, filterValue(cell))
                            }}
                            className="text-dim hover:text-fg invisible group-hover/cell:visible"
                          >
                            <Filter className="size-2.5" />
                          </button>
                        )}
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export function Pager({ offset, limit, shown, total, onOffset, onLimit }: { offset: number; limit: number; shown: number; total: number; onOffset: (o: number) => void; onLimit: (l: number) => void }) {
  return (
    <div className="flex items-center gap-1.5 text-2xs">
      <button disabled={offset <= 0} onClick={() => onOffset(Math.max(0, offset - limit))} className="border-line bg-surface rounded border px-1.5 py-0.5 disabled:opacity-40">
        prev
      </button>
      <span className="num text-dim whitespace-nowrap">
        {total ? `${n(offset + 1)}–${n(offset + shown)}` : '0'} of {n(total)}
      </span>
      <button disabled={offset + shown >= total} onClick={() => onOffset(offset + limit)} className="border-line bg-surface rounded border px-1.5 py-0.5 disabled:opacity-40">
        next
      </button>
      <select value={limit} onChange={(e) => onLimit(Number(e.target.value))} className="border-line rounded border px-1 py-0.5">
        {[...new Set([limit, ...LIMITS])].sort((a, b) => a - b).map((l) => (
          <option key={l} value={l}>
            {l}
          </option>
        ))}
      </select>
    </div>
  )
}

export function DataGrid({
  id,
  url,
  query = {},
  fixed = [],
  limit = 50,
  live = false,
  onRow,
  onPlot,
  link,
  toolbar,
  render,
  initial,
}: {
  id: string
  url: string
  query?: Record<string, string | number | boolean | null | undefined>
  fixed?: string[]
  limit?: number
  live?: boolean
  onRow?: (row: Cell[], grid: Grid) => void
  onPlot?: (column: string, filters: string[]) => void
  link?: (col: GridColumn, cell: Cell, row: Cell[]) => string | null | undefined
  toolbar?: ReactNode
  render?: (grid: Grid) => ReactNode
  initial?: { sort: string; desc: boolean }
}) {
  const g = useGridState(id, limit)
  const sort = g.sort ?? initial?.sort ?? null
  const desc = g.sort ? g.desc : (initial?.desc ?? false)
  const filters = [...fixed, ...g.filters]
  const state = useApi<Grid>(`${url}${qs({ ...query, f: filters, sort, desc, offset: g.offset, limit: g.limit })}`, { live })
  const grid = state.data
  const pinned = grid?.keys ? grid.keys.every((k) => filters.some((f) => f.startsWith(`${k}:`))) : false
  return (
    <div className="w-fit max-w-full min-w-80 space-y-1.5">
      <div className="flex flex-wrap items-center gap-2">
        {toolbar}
        {g.filters.map((f, i) => (
          <button key={f} onClick={() => g.update({ filters: g.filters.filter((_, j) => j !== i) })} className="bg-raised inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-2xs">
            <span className="num">{f.replace(':', ' = ')}</span>
            <X className="size-2.5" />
          </button>
        ))}
        {grid?.game_date && (
          <span className="text-dim num text-2xs">
            snapshot {grid.seq} of {grid.last_seq} · {grid.game_date.text}
          </span>
        )}
        {grid && (grid.offset > 0 || grid.total > grid.rows.length) && (
          <div className="ml-auto">
            <Pager offset={g.offset} limit={g.limit} shown={grid.rows.length} total={grid.total} onOffset={(o) => g.update({ offset: o })} onLimit={(l) => g.update({ limit: l })} />
          </div>
        )}
      </div>
      {state.error ? (
        <ErrorState error={state.error} onRetry={state.reload} />
      ) : !grid ? (
        <Card className="bg-raised h-16 animate-pulse" />
      ) : render ? (
        render(grid)
      ) : (
        <div className={cn(state.stale && 'stale')}>
          <GridTable
            grid={grid}
            sort={sort}
            desc={desc}
            onSort={(name) => (sort !== name ? g.update({ sort: name, desc: false }) : desc ? g.update({ sort: null, desc: false }) : g.update({ sort: name, desc: true }))}
            onFilter={(name, value) => g.update({ filters: [...g.filters.filter((f) => !f.startsWith(`${name}:`)), `${name}:${value}`] })}
            onRow={onRow ? (row) => onRow(row, grid) : undefined}
            plottable={pinned}
            onPlot={onPlot ? (c) => onPlot(c, filters) : undefined}
            link={link}
            hidden={fixed.map((f) => f.split(':')[0])}
          />
        </div>
      )}
    </div>
  )
}

function Pairs({ grid, idx }: { grid: Grid; idx: number[] }) {
  const row = grid.rows[0]
  return (
    <Card className="w-fit max-w-full overflow-hidden">
      <div className="tablewrap">
        <table className="text-xs">
          <tbody>
            {idx.map((i) => (
              <tr key={grid.columns[i].name} className="border-line/60 border-b last:border-0">
                <td className="text-dim px-2 py-0.5 whitespace-nowrap">{grid.columns[i].label}</td>
                <td className={cn('px-2 py-0.5 whitespace-nowrap', right(grid.columns[i]) && 'num')}>
                  <CellValue col={grid.columns[i]} cell={row[i]} run={grid.run} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export function Record({ grid }: { grid: Grid }) {
  if (grid.rows.length !== 1) return <GridTable grid={grid} />
  const sections: { group: string | null; idx: number[] }[] = []
  grid.columns.forEach((c, i) => {
    const g = c.group ?? null
    const last = sections[sections.length - 1]
    if (last && last.group === g) last.idx.push(i)
    else sections.push({ group: g, idx: [i] })
  })
  return (
    <div className="flex flex-wrap items-start gap-4">
      {sections.map((s) => (
        <div key={s.group ?? ''} className="min-w-0">
          {s.group && <div className="text-dim mb-1 text-2xs">{s.group}</div>}
          <Pairs grid={grid} idx={s.idx} />
        </div>
      ))}
    </div>
  )
}
