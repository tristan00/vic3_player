import { ArrowDown, ArrowUp, Filter, LineChart as PlotIcon, X } from 'lucide-react'
import { Fragment, useState, type ReactNode } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Card, ErrorState } from '@/components/primitives'
import { qs, useApi, type Cell, type Grid, type GridColumn } from '@/lib/api'
import { cn, label, n, num, when } from '@/lib/format'

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

export function CellValue({ col, cell, run, link, seq }: { col: GridColumn; cell: Cell; run?: number | null; link?: string | null; seq?: number | null }) {
  const [params] = useSearchParams()
  const { run: routeRun } = useParams()
  let to = link === undefined ? href(col, cell, run) : link
  const at = seq ?? params.get('seq')
  if (to && (col.kind === 'ref' || col.kind === 'kind') && at != null && !to.includes('seq=')) to += `${to.includes('?') ? '&' : '?'}seq=${at}`
  if (to && col.kind === 'action') to += qs({ scope: params.get('scope') ?? (run == null && !routeRun ? undefined : `run:${run ?? routeRun}`) })
  let shown: ReactNode
  if (cell.ref) shown = <>{cell.ref.label ?? cell.ref.id}{col.kind === 'ref' && cell.ref.label && <span className="text-dim ml-1 text-2xs">#{cell.ref.id}</span>}</>
  else if (col.kind === 'time' && cell.text) shown = when(cell.text)
  else if (cell.text !== null && cell.text !== undefined) shown = cell.text
  else if (cell.num !== null && cell.num !== undefined) shown = ['predicted_change', 'gap'].includes(col.name) ? String(Number(cell.num.toPrecision(8))) : num(cell.num)
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
  compactParams = true,
}: {
  grid: Grid
  hidden?: string[]
  compactParams?: boolean
  sort?: string | null
  desc?: boolean
  onSort?: (name: string) => void
  onFilter?: (name: string, value: string) => void
  onRow?: (row: Cell[]) => void
  plottable?: boolean
  onPlot?: (column: string) => void
  link?: (col: GridColumn, cell: Cell, row: Cell[]) => string | null | undefined
}) {
  const params = grid.columns.map((c, i) => ({ c, i })).filter(({ c }) => compactParams && c.group === 'params' && !hidden.includes(c.name))
  const shown = grid.columns.map((c, i) => ({ c, i })).filter(({ c }) => !hidden.includes(c.name) && !(compactParams && c.group === 'params'))
  const cols = shown.map(({ c }) => c)
  const grouped = !params.length && cols.some((c) => c.group)
  const parameterAfter = Math.max(0, cols.findIndex((c) => c.name === 'action'))
  const before = new Map(grid.columns.map((c, i) => [c.name, i]))
  const snapshotColumn = grid.columns.findIndex((c) => c.name === 'seq' || c.name === 'before_seq')
  if (!grid.rows.length) return <Card className="text-dim w-fit px-3 py-2 text-xs">0 rows</Card>
  const first = (k: number) => k === 0 && 'bg-surface sticky left-0 z-[1]'
  return (
    <Card className="w-full max-w-full overflow-hidden">
      <div className="tablewrap max-h-[70vh]">
        <table className="border-collapse text-xs">
          <thead className="bg-surface sticky top-0 z-10">
            {grouped && (
              <tr className="border-line border-b">
                {groups(cols).map((g, i) => (
                  <th key={i} colSpan={g.span} className={cn('text-dim px-2 py-1 text-left text-2xs font-medium whitespace-nowrap', i > 0 && 'border-line border-l')}>
                    {g.group ? label(g.group) : ''}
                  </th>
                ))}
              </tr>
            )}
            <tr className="border-line border-b">
              {cols.map((c, k) => (
                <Fragment key={c.name}><th scope="col" aria-sort={sort === c.name ? desc ? 'descending' : 'ascending' : undefined} title={c.name} className={cn('text-dim px-2 py-1 font-medium whitespace-nowrap', right(c) ? 'text-right' : 'text-left', first(k))}>
                  <span className="inline-flex items-center gap-1">
                    {onSort ? (
                      <button type="button" onClick={() => onSort(c.name)} className="hover:text-fg inline-flex items-center gap-0.5">
                        {label(c.label)}
                        {sort === c.name && (desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
                      </button>
                    ) : (
                      label(c.label)
                    )}
                    {plottable && onPlot && c.kind === 'number' && (
                      <button type="button" onClick={() => onPlot(c.name)} className="hover:text-fg opacity-60" aria-label={`plot ${c.name}`}>
                        <PlotIcon className="size-3" />
                      </button>
                    )}
                  </span>
                </th>{params.length > 0 && k === parameterAfter && <th className="text-left font-medium whitespace-nowrap">Targets & parameters</th>}</Fragment>
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
                    <Fragment key={i}><td className={cn('group/cell px-2 py-1 align-top', ['detail', 'block'].includes(col.name) ? 'min-w-64 whitespace-normal' : 'whitespace-nowrap', right(col) && 'num text-right', changed && 'bg-accent-soft', first(k))}>
                      <span className="inline-flex items-start gap-1">
                        <CellValue col={col} cell={cell} run={grid.run} seq={row[snapshotColumn]?.ref?.id ?? grid.seq} link={link ? link(col, cell, row) : undefined} />
                        {k === 0 && onRow && <button className="linka ml-2" onClick={(e) => { e.stopPropagation(); onRow(row) }}>Inspect</button>}
                        {onFilter && (
                          <button
                            type="button"
                            aria-label={`filter ${col.name}`}
                            onClick={(e) => {
                              e.stopPropagation()
                              onFilter(col.name, col.kind === 'date' && cell.num != null ? String(cell.num) : filterValue(cell))
                            }}
                            className="text-dim hover:text-fg shrink-0 opacity-0 group-hover/cell:opacity-100 focus:opacity-100"
                          >
                            <Filter className="size-2.5" />
                          </button>
                        )}
                      </span>
                    </td>{params.length > 0 && k === parameterAfter && <td className="align-top"><div className="space-y-1 min-w-64">{params.filter(({ i: p }) => cellText(row[p]) !== '∅').map(({ c, i: p }) => <div key={c.name}><span className="text-dim mr-2">{label(c.label)}:</span><CellValue col={c} cell={row[p]} run={grid.run} seq={row[snapshotColumn]?.ref?.id ?? grid.seq} /></div>)}</div></td>}</Fragment>
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
      <select aria-label="Rows per page" value={limit} onChange={(e) => onLimit(Number(e.target.value))} className="border-line rounded border px-1 py-0.5">
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
  columnGroup,
  columns,
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
  columnGroup?: string
  columns?: string[]
}) {
  const g = useGridState(id, limit)
  const [search, setSearch] = useSearchParams()
  const [filterColumn, setFilterColumn] = useState('')
  const [filterText, setFilterText] = useState('')
  const group = search.get(`${id}.group`) ?? columnGroup ?? ''
  const setOption = (key: string, values: string[]) => {
    const next = new URLSearchParams(search)
    next.delete(`${id}.${key}`)
    values.forEach((v) => next.append(`${id}.${key}`, v))
    setSearch(next, { replace: true })
  }
  const sort = g.sort ?? initial?.sort ?? null
  const desc = g.sort ? g.desc : (initial?.desc ?? false)
  const filters = [...fixed, ...g.filters]
  const state = useApi<Grid>(`${url}${qs({ ...query, f: filters, sort, desc, offset: g.offset, limit: g.limit })}`, { live })
  const grid = state.data
  const hidden = search.has(`${id}.hide`) ? search.getAll(`${id}.hide`).filter(Boolean) : grid?.columns.filter((c) => columns && !columns.includes(c.name) && c.group !== 'params').map((c) => c.name) ?? []
  const pinned = grid?.keys ? grid.keys.every((k) => filters.some((f) => f.startsWith(`${k}:`))) : false
  return (
    <div className="max-w-full min-w-0 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {toolbar}
        {grid && !render && <>
          <details className="grid-control">
            <summary>Filter</summary>
            <form className="control-panel flex flex-wrap gap-2" onSubmit={(e) => {
              e.preventDefault()
              if (!filterColumn || !filterText) return
              g.update({ filters: [...g.filters.filter((f) => !f.startsWith(`${filterColumn}:`)), `${filterColumn}:${filterText}`] })
              e.currentTarget.closest('details')?.removeAttribute('open')
            }}>
              <select aria-label="Filter column" value={filterColumn} onChange={(e) => setFilterColumn(e.target.value)}><option value="">Choose column</option>{grid.columns.map((c) => <option key={c.name} value={c.name}>{label(c.name)}</option>)}</select>
              <input aria-label="Filter value" placeholder="Exact value or entity ID" value={filterText} onChange={(e) => setFilterText(e.target.value)} />
              <button disabled={!filterColumn || !filterText}>Apply filter</button>
              <p className="text-dim basis-full">Matches all rows, including other pages. Use an ID for entities, or ∅ for empty values.</p>
            </form>
          </details>
          <details className="grid-control">
            <summary>Columns</summary>
            <div className="control-panel max-h-80 overflow-auto space-y-2">
              <button onClick={() => { const next = new URLSearchParams(search); next.set(`${id}.hide`, ''); next.set(`${id}.group`, ''); setSearch(next, { replace: true }) }}>Show all columns</button>
              <button className="ml-3" onClick={() => { const next = new URLSearchParams(search); next.delete(`${id}.hide`); next.delete(`${id}.group`); setSearch(next, { replace: true }) }}>Reset columns</button>
              {grid.columns.filter((c) => !fixed.some((f) => f.startsWith(`${c.name}:`))).map((c) => <label key={c.name} className="flex items-center gap-2"><input type="checkbox" checked={!hidden.includes(c.name) && (!group || c.group === group || c.kind === 'ref' || c === grid.columns[0])} onChange={(e) => {
                const effective = [...new Set([...hidden, ...grid.columns.filter((c) => group && c.group !== group && c.kind !== 'ref' && c !== grid.columns[0]).map((c) => c.name)])]
                const next = new URLSearchParams(search)
                next.delete(`${id}.hide`)
                const values = e.target.checked ? effective.filter((h) => h !== c.name) : [...effective, c.name]
                for (const value of values.length ? values : ['']) next.append(`${id}.hide`, value)
                next.set(`${id}.group`, '')
                setSearch(next, { replace: true })
              }} />{label(c.name)}</label>)}
            </div>
          </details>
          {grid.columns.some((c) => c.group && c.group !== 'params') && <label className="flex items-center gap-2 text-xs">Column group<select aria-label="Column group" value={group} onChange={(e) => {
            const next = new URLSearchParams(search)
            next.set(`${id}.group`, e.target.value)
            next.set(`${id}.hide`, '')
            setSearch(next, { replace: true })
          }}><option value="">All groups</option>{[...new Set(grid.columns.map((c) => c.group).filter((v): v is string => !!v && v !== 'params'))].map((v) => <option key={v} value={v}>{label(v)}</option>)}</select></label>}
          {grid.columns.some((c) => c.group === 'params') && <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={search.get(`${id}.params`) !== 'columns'} onChange={(e) => setOption('params', e.target.checked ? [] : ['columns'])} />Group parameters</label>}
        </>}
        {g.filters.map((f, i) => (
          <button key={f} onClick={() => g.update({ filters: g.filters.filter((_, j) => j !== i) })} className="bg-raised inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-2xs">
            <span className="num">{f.replace(':', ' = ')}</span>
            <X className="size-2.5" />
          </button>
        ))}
        {grid?.game_date && (
          <span className="text-dim num text-2xs">
            <Link className="linka" to={`/runs/${grid.run}/snapshots/${grid.seq}`}>Snapshot {grid.seq}</Link> of {grid.last_seq} · {grid.game_date.text}
          </span>
        )}
        {grid && !render && (
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
            hidden={[...fixed.map((f) => f.split(':')[0]), ...hidden, ...grid.columns.filter((c) => group && c.group !== group && c.kind !== 'ref' && c !== grid.columns[0]).map((c) => c.name)]}
            compactParams={search.get(`${id}.params`) !== 'columns'}
          />
        </div>
      )}
    </div>
  )
}

export function Record({ grid, onPlot }: { grid: Grid; onPlot?: (column: string) => void }) {
  if (grid.rows.length !== 1) return <GridTable grid={grid} />
  const sections: { group: string | null; idx: number[] }[] = []
  grid.columns.forEach((c, i) => {
    const g = c.group ?? null
    const last = sections[sections.length - 1]
    if (last && last.group === g) last.idx.push(i)
    else sections.push({ group: g, idx: [i] })
  })
  const seq = grid.rows[0][grid.columns.findIndex((c) => c.name === 'before_seq')]?.ref?.id ?? grid.seq
  return (
    <Card className="max-w-full overflow-hidden"><div className="tablewrap"><table className="text-xs">
      {sections.map((s, section) => <tbody key={section}>
        {s.group && <tr><th colSpan={2} className="bg-raised text-left capitalize">{label(s.group)}</th></tr>}
        {s.idx.map((i) => <tr key={grid.columns[i].name} className="border-line/60 border-b last:border-0">
          <th scope="row" className="text-dim text-left font-medium w-48">{label(grid.columns[i].label)}</th>
          <td><CellValue col={grid.columns[i]} cell={grid.rows[0][i]} run={grid.run} seq={seq} />
            {onPlot && grid.columns[i].kind === 'number' && <button className="linka ml-3" aria-label={`plot ${grid.columns[i].name}`} onClick={() => onPlot(grid.columns[i].name)}><PlotIcon className="size-3" /></button>}
          </td>
        </tr>)}
      </tbody>)}
    </table></div></Card>
  )
}
