import { useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useApi } from './api'
import { useWidth } from './charts'
import { label, num } from './format'
import { Entity, Waiting } from './Grid'

type Key = string | { kind: string; id: number; label: string }
type Leaf = { [name: string]: any; building: number | null; values: (number | null)[]; weights?: (number | null)[] }
type Sheet = { dates: string[]; rows: Leaf[]; figures?: string[] }
type Node = { id: string; cells: Key[]; leaves: Leaf[]; values: (number | null)[]; rows: Node[]; building: number | null }

const PLACED = [['type', 'sector'], ['state']]
const SPLIT = { type: PLACED, state: [['state'], ['type', 'sector']], building: [['type', 'state', 'sector']] }
const GRAINS: Record<string, Record<string, string[][]>> = {
  levels: SPLIT,
  methods: { type: [['type', 'method_group', 'method'], ['state']], building: [['type', 'state', 'method_group', 'method']] },
  staffing: SPLIT,
  money: SPLIT,
  ownership: { owner: [['owner'], ...PLACED], type: [['type', 'sector'], ['owner'], ['state']] },
  queue: { funder: [['funder'], ...PLACED], type: [['type', 'sector'], ['funder'], ['state']] },
}
const VIEWS = Object.keys(GRAINS)
const HEADS: Record<string, string> = { sector: 'group', method_group: 'method group' }
const WIDTHS: Record<string, number> = { type: 230, state: 200, sector: 170, method_group: 170, method: 200, owner: 230, funder: 230 }
const FACETS = ['sector', 'expandable']
const CELLS: Record<string, number> = { money: 46, staffing: 40 }

function text(key: Key) {
  return typeof key === 'string' ? label(key) : label(key.label)
}

function ident(key: Key) {
  return typeof key === 'string' ? key : `${key.kind} ${key.id}`
}

function compact(value: number) {
  const size = Math.abs(value)
  return size >= 1e6 ? `${(value / 1e6).toFixed(1)}M` : size >= 1e4 ? `${Math.round(value / 1e3)}k` : size >= 1e3 ? `${(value / 1e3).toFixed(1)}k` : String(Math.round(value))
}

function folded(leaves: Leaf[], size: number) {
  const out: (number | null)[] = []
  for (let at = 0; at < size; at += 1) {
    let sum = 0
    let weight = 0
    let seen = false
    for (const leaf of leaves) {
      const value = leaf.values[at]
      if (value === null) continue
      const share = leaf.weights ? (leaf.weights[at] ?? 0) : 1
      sum += value * share
      weight += share
      seen = true
    }
    out.push(!seen ? null : leaves[0].weights ? (weight ? sum / weight : null) : sum)
  }
  return out
}

function grown(leaves: Leaf[], levels: string[][], path: string, size: number): Node[] {
  if (!levels.length) return []
  const groups = new Map<string, Leaf[]>()
  for (const leaf of leaves) {
    const id = levels[0].map((name) => ident(leaf[name])).join('|')
    if (!groups.has(id)) groups.set(id, [])
    groups.get(id)!.push(leaf)
  }
  return [...groups].map(([id, inside]) => ({ id: `${path}/${id}`, cells: levels[0].map((name) => inside[0][name]), leaves: inside, values: folded(inside, size), rows: grown(inside, levels.slice(1), `${path}/${id}`, size), building: levels.length === 1 && inside.length === 1 ? inside[0].building : null }))
}

function fitted(dates: string[], room: number) {
  const all = dates.map((_, index) => index)
  const kept = (wanted: (date: string) => boolean) => all.filter((index) => index === 0 || index === dates.length - 1 || (wanted(dates[index]) && dates[index].slice(0, 7) !== dates[index - 1].slice(0, 7)))
  const years = (step: number) => kept((date) => date.slice(5, 7) === '01' && Number(date.slice(0, 4)) % step === 0)
  return [all, kept((date) => date.slice(5, 7) === '01' || date.slice(5, 7) === '07'), years(1), years(2), years(5)].find((found) => found.length <= room) ?? years(10)
}

function flip(list: string[], key: string) {
  return list.includes(key) ? list.filter((other) => other !== key) : [...list, key]
}

function Ledger({ run, found, levels, shape, cell, total, every }: { run: number; found: Sheet; levels: string[][]; shape: (value: number) => string; cell: number; total: boolean; every: boolean }) {
  const [box, width] = useWidth()
  const [words, setWords] = useState('')
  const [open, setOpen] = useState<string[]>([])
  const [chosen, setChosen] = useState<Record<string, string[]>>({})
  const [order, setOrder] = useState<{ by: number; named: boolean; desc: boolean }>({ by: 0, named: true, desc: false })
  const size = found.dates.length
  const heads = Array.from({ length: Math.max(...levels.map((level) => level.length)) }, (_, column) => levels.find((level) => level[column])![column])
  const widths = heads.map((_, column) => Math.max(...levels.map((level) => WIDTHS[level[column]] ?? 0)))
  const lefts = widths.map((_, column) => widths.slice(0, column).reduce((sum, wide) => sum + wide, 0))
  const labels = widths.reduce((sum, wide) => sum + wide, 0)
  const shown = every ? found.dates.map((_, index) => index) : fitted(found.dates, Math.max(1, Math.floor((width - 2 - labels) / cell)))
  const passes = (leaf: Leaf, except?: string) => FACETS.every((name) => name === except || !chosen[name]?.length || chosen[name].includes(leaf[name]))
  const facets = FACETS.map((name) => {
    const counts = new Map<string, Set<string>>()
    for (const leaf of found.rows) if (leaf[name] && !counts.has(leaf[name])) counts.set(leaf[name], new Set())
    for (const leaf of found.rows) if (leaf[name] && passes(leaf, name)) counts.get(leaf[name])!.add(leaf.type)
    return { name, values: [...counts].map(([value, types]) => [value, types.size] as [string, number]).sort((a, b) => a[0].localeCompare(b[0])) }
  })
  const tree = useMemo(() => grown(found.rows.filter((leaf) => passes(leaf)), levels, '', size), [found, levels, chosen])
  const wanted = words.toLowerCase().split(/\s+/).filter(Boolean)
  const top = tree.filter((node) => wanted.every((word) => node.cells.map(text).join(' ').toLowerCase().includes(word)))
  const sorted = (nodes: Node[]) => {
    const value = (node: Node) => (order.named ? (node.cells[order.by] === undefined ? null : text(node.cells[order.by]).toLowerCase()) : node.values[order.by])
    return [...nodes].sort((a, b) => {
      const left = value(a)
      const right = value(b)
      if (left === right) return a.cells.map(text).join(' / ').localeCompare(b.cells.map(text).join(' / '))
      if (left === null) return 1
      if (right === null) return -1
      return (left < right ? -1 : 1) * (order.desc ? -1 : 1)
    })
  }
  const lines: { node: Node; depth: number }[] = []
  const list = (nodes: Node[], depth: number) =>
    sorted(nodes).forEach((node) => {
      lines.push({ node, depth })
      if (open.includes(node.id)) list(node.rows, depth + 1)
    })
  list(top, 0)
  const sum = total && top.length ? folded(top.flatMap((node) => node.leaves), size) : null
  const press = (by: number, named: boolean) => setOrder({ by, named, desc: order.by === by && order.named === named ? !order.desc : !named })
  const arrow = (by: number, named: boolean) => order.by === by && order.named === named && <span className="arrow">{order.desc ? '▼' : '▲'}</span>
  const years = shown.map((at) => found.dates[at].slice(0, 4))
  const entry = (node: Node, column: number): ReactNode => {
    const key = node.cells[column]
    if (key === undefined) return null
    if (column === 0 && node.building !== null) return <Link to={`/runs/${run}/e/building/${node.building}`}>{text(key)}</Link>
    return typeof key === 'string' ? text(key) : <Entity run={run} kind={key.kind} id={key.id} name={key.label} />
  }
  return (
    <div className="grid" ref={box}>
      <div className="grid-tools">
        <input type="search" placeholder="filter" value={words} onChange={(event) => setWords(event.target.value)} />
        {facets
          .filter((facet) => facet.values.length > 1)
          .map((facet) => (
            <span key={facet.name} className="facet">
              <small>{label(HEADS[facet.name] ?? facet.name)}</small>
              {facet.values.map(([value, count]) => (
                <button key={value} className={chosen[facet.name]?.includes(value) ? 'on' : ''} onClick={() => setChosen({ ...chosen, [facet.name]: flip(chosen[facet.name] ?? [], value) })}>
                  {label(value)} <small>{count}</small>
                </button>
              ))}
            </span>
          ))}
        <span className="count">{num(top.length)} rows</span>
      </div>
      <div className="grid-box">
        <table className="ledger" style={{ width: every ? Math.max(width - 2, labels + shown.length * cell) : width - 2 }}>
          <colgroup>
            {widths.map((wide, column) => (
              <col key={column} style={{ width: wide }} />
            ))}
            {shown.map((at) => (
              <col key={at} />
            ))}
          </colgroup>
          <thead>
            <tr className="groups">
              {heads.map((name, column) => (
                <th key={name} className="pinned" style={{ left: lefts[column] }} />
              ))}
              {shown.map((at, position) =>
                position === 0 || years[position - 1] !== years[position] ? (
                  <th key={at} className="group" colSpan={years.filter((year) => year === years[position]).length}>
                    {years[position]}
                  </th>
                ) : null,
              )}
            </tr>
            <tr>
              {heads.map((name, column) => (
                <th key={name} className="pinned" style={{ left: lefts[column] }} onClick={() => press(column, true)}>
                  {label(HEADS[name] ?? name)}
                  {arrow(column, true)}
                </th>
              ))}
              {shown.map((at) => (
                <th key={at} className="right" onClick={() => press(at, false)}>
                  {found.dates[at].endsWith('-01') ? found.dates[at].slice(5, 7) : found.dates[at].slice(5)}
                  {arrow(at, false)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sum && (
              <tr className="total">
                {heads.map((name, column) => (
                  <td key={name} className="pinned" style={{ left: lefts[column] }}>
                    {column === 0 && 'total'}
                  </td>
                ))}
                {shown.map((at) => (
                  <td key={at} className="right">
                    {sum[at] === null ? '' : shape(sum[at]!)}
                  </td>
                ))}
              </tr>
            )}
            {lines.map(({ node, depth }) => (
              <tr key={node.id} className={depth ? 'inner' : ''}>
                {heads.map((name, column) => (
                  <td key={name} className="pinned" style={column === 0 ? { left: 0, paddingLeft: 8 + depth * 18 } : { left: lefts[column] }}>
                    {column === 0 &&
                      levels.length > 1 &&
                      (node.rows.length > 0 ? (
                        <a className="twist" onClick={() => setOpen(flip(open, node.id))}>
                          {open.includes(node.id) ? '▾' : '▸'}
                        </a>
                      ) : (
                        <span className="twist" />
                      ))}
                    {entry(node, column)}
                  </td>
                ))}
                {shown.map((at) => (
                  <td key={at} className="right">
                    {node.values[at] === null ? '' : shape(node.values[at]!)}
                  </td>
                ))}
              </tr>
            ))}
            {!lines.length && (
              <tr>
                <td colSpan={heads.length + shown.length} className="none">
                  no rows
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function Buildings({ run, live }: { run: number; live: boolean }) {
  const [query, setQuery] = useSearchParams()
  const view = VIEWS.includes(query.get('view') ?? '') ? query.get('view')! : VIEWS[0]
  const grains = Object.keys(GRAINS[view])
  const by = grains.includes(query.get('by') ?? '') ? query.get('by')! : grains[0]
  const figure = query.get('figure') ?? 'goods_sales'
  const every = query.get('dates') === 'all'
  const found = useApi<Sheet>(`/api/runs/${run}/buildings/${view}${view === 'money' ? `?figure=${figure}` : ''}`, live ? 15000 : 0)
  const change = (name: string, value: string | null) => {
    const next = new URLSearchParams(query)
    if (value === null) next.delete(name)
    else next.set(name, value)
    setQuery(next, { replace: true })
  }
  return (
    <>
      <div className="tabs sub">
        {VIEWS.map((name) => (
          <a key={name} className={name === view ? 'on' : ''} onClick={() => setQuery({ tab: 'buildings', ...(name === VIEWS[0] ? {} : { view: name }), ...(every ? { dates: 'all' } : {}) })}>
            {name}
          </a>
        ))}
      </div>
      <div className="lead">
        <span className="choice">
          {grains.map((name) => (
            <a key={name} className={name === by ? 'on' : ''} onClick={() => change('by', name === grains[0] ? null : name)}>
              by {name}
            </a>
          ))}
        </span>
        {view === 'money' && found.data?.figures && (
          <label>
            figure{' '}
            <select value={figure} onChange={(event) => change('figure', event.target.value)}>
              {found.data.figures.map((name) => (
                <option key={name} value={name}>
                  {label(name)}
                </option>
              ))}
            </select>
          </label>
        )}
        <span>dates</span>
        <span className="choice">
          <a className={every ? '' : 'on'} onClick={() => change('dates', null)}>
            fitted
          </a>
          <a className={every ? 'on' : ''} onClick={() => change('dates', 'all')}>
            all
          </a>
        </span>
      </div>
      <Waiting loaded={found}>{() => <Ledger key={`${view} ${by}`} run={run} found={found.data!} levels={GRAINS[view][by]} shape={view === 'money' ? compact : view === 'staffing' ? (value) => `${Math.round(value)}%` : String} cell={CELLS[view] ?? 36} total={view !== 'methods'} every={every} />}</Waiting>
    </>
  )
}
