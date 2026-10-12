import { useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useApi } from './api'
import { useWidth } from './charts'
import { label } from './format'
import { Entity, Waiting } from './Grid'

type Key = string | { kind: string; id: number; label: string }
type Leaf = { [name: string]: any; building: number | null; values: (number | null)[] }
type Sheet = { dates: string[]; rows: Leaf[]; figures?: string[] }
type Shape = { section?: string; row: string; inner: string }
type Node = { id: string; key: Key; values: number[]; rows: Node[]; building: number | null }
type Line = { id: string; cells: Key[]; marks: (string | null)[]; rows: Line[]; building: number | null; changes: number; first: number }

const PLACED: Record<string, Shape> = { type: { section: 'sector', row: 'type', inner: 'state' }, state: { row: 'state', inner: 'type' } }
const VIEWS: Record<string, { name: string; by?: Record<string, Shape> }> = {
  levels: { name: 'levels', by: PLACED },
  unstaffed: { name: 'unstaffed levels', by: PLACED },
  methods: { name: 'production methods' },
  money: { name: 'money', by: PLACED },
  ownership: { name: 'ownership', by: { owner: { row: 'owner', inner: 'type' }, type: { section: 'sector', row: 'type', inner: 'owner' } } },
  queue: { name: 'construction queue' },
}
const NAMED = ['type', 'sector', 'state', 'owner', 'funder', 'method_group', 'method']
const NAME = 250
const CELL = 36
const STEPS = [1, 2, 5, 10]

function text(key: Key) {
  return label(typeof key === 'string' ? key : key.label)
}

function ident(key: Key) {
  return typeof key === 'string' ? key : `${key.kind} ${key.id}`
}

function whole(value: number) {
  return value ? String(value) : ''
}

function tenths(value: number) {
  return Math.abs(value) < 0.05 ? '' : Math.abs(value) >= 100 ? String(Math.round(value)) : value.toFixed(1)
}

function compact(value: number) {
  const size = Math.abs(value)
  return size < 0.5 ? '' : size >= 1e6 ? `${(value / 1e6).toFixed(1)}M` : size >= 1e4 ? `${Math.round(value / 1e3)}k` : size >= 1e3 ? `${(value / 1e3).toFixed(1)}k` : String(Math.round(value))
}

function flip(list: string[], key: string) {
  return list.includes(key) ? list.filter((other) => other !== key) : [...list, key]
}

function named(run: number, key: Key, building: number | null): ReactNode {
  if (building !== null) return <Link to={`/runs/${run}/e/building/${building}`}>{text(key)}</Link>
  return typeof key === 'string' ? text(key) : <Entity run={run} kind={key.kind} id={key.id} name={key.label} />
}

function grouped(leaves: Leaf[], names: string[], path: string, size: number): Node[] {
  if (!names.length) return []
  const found = new Map<string, Leaf[]>()
  for (const leaf of leaves) {
    const id = ident(leaf[names[0]])
    if (!found.has(id)) found.set(id, [])
    found.get(id)!.push(leaf)
  }
  return [...found].map(([id, inside]) => {
    const values = new Array<number>(size).fill(0)
    for (const leaf of inside) for (let at = 0; at < size; at += 1) values[at] += leaf.values[at] ?? 0
    return { id: `${path}/${id}`, key: inside[0][names[0]], values, rows: grouped(inside, names.slice(1), `${path}/${id}`, size), building: names.length === 1 && inside.length === 1 ? inside[0].building : null }
  })
}

function yearly(dates: string[], room: number) {
  const last = dates.length - 1
  const starts = dates.map((_, at) => at).filter((at) => at === 0 || at === last || dates[at].slice(0, 4) !== dates[at - 1].slice(0, 4))
  const every = (step: number) => starts.filter((at) => at === 0 || at === last || Number(dates[at].slice(0, 4)) % step === 0)
  return every(STEPS.find((step) => every(step).length <= room) ?? 10)
}

function Matrix({ run, found, shape, show }: { run: number; found: Sheet; shape: Shape; show: (value: number) => string }) {
  const [box, width] = useWidth()
  const [open, setOpen] = useState<string[]>([])
  const [order, setOrder] = useState<{ by: number | null; desc: boolean }>({ by: null, desc: false })
  const size = found.dates.length
  const tree = useMemo(() => grouped(found.rows, [...(shape.section ? [shape.section] : []), shape.row, shape.inner], '', size), [found, shape])
  const shown = yearly(found.dates, Math.max(2, Math.floor((width - 2 - NAME) / CELL)))
  const sorted = (nodes: Node[]) =>
    [...nodes].sort((a, b) => {
      const sign = order.desc ? -1 : 1
      const names = text(a.key).localeCompare(text(b.key))
      return order.by === null ? names * sign : (a.values[order.by] - b.values[order.by]) * sign || names
    })
  const press = (by: number | null) => setOrder({ by, desc: order.by === by ? !order.desc : by !== null })
  const arrow = (by: number | null) => order.by === by && <span className="arrow">{order.desc ? '▼' : '▲'}</span>
  const line = (id: string, kind: string, first: ReactNode, values: number[]) => (
    <tr key={id} className={kind}>
      <td>{first}</td>
      {shown.map((at) => (
        <td key={at} className="right">
          {show(values[at])}
        </td>
      ))}
    </tr>
  )
  const block = (nodes: Node[]) =>
    sorted(nodes).flatMap((node) => [
      line(
        node.id,
        '',
        <>
          <a className="twist" onClick={() => setOpen(flip(open, node.id))}>
            {open.includes(node.id) ? '▾' : '▸'}
          </a>
          {named(run, node.key, null)}
        </>,
        node.values,
      ),
      ...(open.includes(node.id) ? sorted(node.rows).map((inner) => line(inner.id, 'inner', named(run, inner.key, inner.building), inner.values)) : []),
    ])
  const total = new Array<number>(size).fill(0)
  for (const node of tree) for (let at = 0; at < size; at += 1) total[at] += node.values[at]
  return (
    <div className="grid" ref={box}>
      <div className="grid-box">
        <table className="matrix" style={{ width: width - 2 }}>
          <colgroup>
            <col style={{ width: NAME }} />
            {shown.map((at) => (
              <col key={at} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th onClick={() => press(null)}>
                {shape.row}
                {arrow(null)}
              </th>
              {shown.map((at) => (
                <th key={at} className="right" title={found.dates[at]} onClick={() => press(at)}>
                  {found.dates[at].endsWith('-01-01') ? found.dates[at].slice(0, 4) : found.dates[at].slice(2, 7)}
                  {arrow(at)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tree.length > 0 && line('total', 'total', 'total', total)}
            {shape.section ? sorted(tree).flatMap((section) => [line(section.id, 'section', text(section.key), section.values), ...block(section.rows)]) : block(tree)}
            {!tree.length && (
              <tr>
                <td colSpan={shown.length + 1} className="none">
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

function lined(id: string, cells: Key[], marks: (string | null)[], rows: Line[], building: number | null): Line {
  const held = marks.filter((mark, at) => mark !== null && mark !== marks[at - 1])
  return { id, cells, marks, rows, building, changes: held.filter((mark, at) => at > 0 && mark !== held[at - 1]).length, first: marks.findIndex((mark) => mark !== null) }
}

function methods(found: Sheet): Line[] {
  const size = found.dates.length
  const kinds = new Map<string, { cells: Key[]; places: Map<string, { state: Key; building: number | null; marks: (string | null)[] }>; mixes: Map<string, number>[] }>()
  for (const leaf of found.rows) {
    const id = `${leaf.type}/${leaf.method_group}`
    if (!kinds.has(id)) kinds.set(id, { cells: [leaf.type, leaf.method_group], places: new Map(), mixes: Array.from({ length: size }, () => new Map()) })
    const kind = kinds.get(id)!
    const spot = ident(leaf.state)
    if (!kind.places.has(spot)) kind.places.set(spot, { state: leaf.state, building: leaf.building, marks: new Array(size).fill(null) })
    const place = kind.places.get(spot)!
    leaf.values.forEach((levels, at) => {
      if (!levels) return
      place.marks[at] = label(leaf.method)
      kind.mixes[at].set(leaf.method, (kind.mixes[at].get(leaf.method) ?? 0) + levels)
    })
  }
  return [...kinds].map(([id, kind]) =>
    lined(
      id,
      kind.cells,
      kind.mixes.map((mix) => (mix.size ? [...mix].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([name]) => label(name)).join(' · ') : null)),
      [...kind.places].map(([spot, place]) => lined(`${id}/${spot}`, [place.state], place.marks, [], place.building)).sort((a, b) => text(a.cells[0]).localeCompare(text(b.cells[0]))),
      null,
    ),
  )
}

function queued(found: Sheet): Line[] {
  return found.rows.map((leaf) => lined(`${leaf.funder}/${leaf.type}/${ident(leaf.state)}`, [leaf.funder, leaf.type, leaf.state], leaf.values.map((count) => (count ? String(count) : null)), [], null))
}

function Lane({ dates, marks }: { dates: string[]; marks: (string | null)[] }) {
  const size = marks.length
  const spans: { from: number; to: number; mark: string }[] = []
  marks.forEach((mark, at) => {
    const last = spans[spans.length - 1]
    if (mark === null) return
    if (last && last.to === at && last.mark === mark) last.to = at + 1
    else spans.push({ from: at, to: at + 1, mark })
  })
  return (
    <td className="lane">
      {spans.map((span) => (
        <span key={span.from} title={`${span.mark} · ${dates[span.from]} to ${dates[span.to - 1]}`} style={{ left: `${(100 * span.from) / size}%`, width: `calc(${(100 * (span.to - span.from)) / size}% - 1px)` }}>
          {span.mark}
        </span>
      ))}
    </td>
  )
}

function Spans({ run, dates, lines, heads, widths, twist, counted, start }: { run: number; dates: string[]; lines: Line[]; heads: string[]; widths: number[]; twist: number | null; counted: boolean; start: number | 'first' }) {
  const [box, width] = useWidth()
  const [open, setOpen] = useState<string[]>([])
  const [order, setOrder] = useState<{ by: number | 'changes' | 'first'; desc: boolean }>({ by: start, desc: false })
  const size = dates.length
  const years = dates.map((_, at) => at).filter((at) => at === 0 || dates[at].slice(0, 4) !== dates[at - 1].slice(0, 4))
  const room = width - 2 - widths.reduce((sum, wide) => sum + wide, 0) - (counted ? 70 : 0)
  const step = STEPS.find((count) => (room / years.length) * count >= 34) ?? 10
  const rules = years.slice(1).map((at) => `transparent ${(100 * at) / size}%, #e3e7ee ${(100 * at) / size}%, #e3e7ee calc(${(100 * at) / size}% + 1px), transparent calc(${(100 * at) / size}% + 1px)`)
  const sorted = [...lines].sort((a, b) => {
    const sign = order.desc ? -1 : 1
    const names = a.cells.map(text).join(' / ').localeCompare(b.cells.map(text).join(' / '))
    if (typeof order.by === 'number') return text(a.cells[order.by]).localeCompare(text(b.cells[order.by])) * sign || names
    return (a[order.by] - b[order.by]) * sign || names
  })
  const press = (by: number | 'changes' | 'first') => setOrder({ by, desc: order.by === by ? !order.desc : by === 'changes' })
  const arrow = (by: number | 'changes' | 'first') => order.by === by && <span className="arrow">{order.desc ? '▼' : '▲'}</span>
  return (
    <div className="grid" ref={box}>
      <div className="grid-box">
        <table className={counted ? 'spans' : 'spans counts'} style={{ width: width - 2, ['--years' as any]: rules.length ? `linear-gradient(to right, ${rules.join(', ')})` : 'none' }}>
          <colgroup>
            {widths.map((wide, column) => (
              <col key={column} style={{ width: wide }} />
            ))}
            {counted && <col style={{ width: 70 }} />}
            <col />
          </colgroup>
          <thead>
            <tr>
              {heads.map((name, column) => (
                <th key={name} onClick={() => press(column)}>
                  {name}
                  {arrow(column)}
                </th>
              ))}
              {counted && (
                <th className="right" onClick={() => press('changes')}>
                  changes
                  {arrow('changes')}
                </th>
              )}
              <th className="lane" onClick={() => press('first')}>
                {years
                  .filter((at) => at === 0 || Number(dates[at].slice(0, 4)) % step === 0)
                  .map((at) => (
                    <span key={at} style={{ left: `${(100 * at) / size}%` }}>
                      {dates[at].slice(0, 4)}
                    </span>
                  ))}
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.flatMap((line, position) => [
              <tr key={line.id}>
                {line.cells.map((cell, column) => (
                  <td key={column}>
                    {column === twist &&
                      (line.rows.length > 1 ? (
                        <a className="twist" onClick={() => setOpen(flip(open, line.id))}>
                          {open.includes(line.id) ? '▾' : '▸'}
                        </a>
                      ) : (
                        <span className="twist" />
                      ))}
                    {column === 0 && order.by === 0 && position > 0 && text(sorted[position - 1].cells[0]) === text(cell) ? null : named(run, cell, null)}
                  </td>
                ))}
                {counted && <td className="right">{line.changes || ''}</td>}
                <Lane dates={dates} marks={line.marks} />
              </tr>,
              ...(open.includes(line.id)
                ? line.rows.map((inner) => (
                    <tr key={inner.id} className="inner">
                      {line.cells.map((_, column) => (
                        <td key={column}>{column === twist && named(run, inner.cells[0], inner.building)}</td>
                      ))}
                      {counted && <td className="right">{inner.changes || ''}</td>}
                      <Lane dates={dates} marks={inner.marks} />
                    </tr>
                  ))
                : []),
            ])}
            {!sorted.length && (
              <tr>
                <td colSpan={heads.length + (counted ? 2 : 1)} className="none">
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
  const [words, setWords] = useState('')
  const view = (query.get('view') ?? '') in VIEWS ? query.get('view')! : 'levels'
  const shapes = VIEWS[view].by
  const by = shapes ? ((query.get('by') ?? '') in shapes ? query.get('by')! : Object.keys(shapes)[0]) : ''
  const figure = query.get('figure') ?? 'goods_sales'
  const found = useApi<Sheet>(`/api/runs/${run}/buildings/${view}${view === 'money' ? `?figure=${figure}` : ''}`, live ? 15000 : 0)
  const figures = useRef<string[]>([])
  if (found.data?.figures) figures.current = found.data.figures
  const kept = useMemo(() => {
    const wanted = words.toLowerCase().split(/\s+/).filter(Boolean)
    return found.data && { ...found.data, rows: found.data.rows.filter((leaf) => wanted.every((word) => NAMED.some((name) => leaf[name] !== undefined && text(leaf[name]).toLowerCase().includes(word)))) }
  }, [found.data, words])
  const change = (name: string, value: string) => {
    const next = new URLSearchParams(query)
    next.set(name, value)
    setQuery(next, { replace: true })
  }
  return (
    <>
      <div className="tabs sub">
        {Object.entries(VIEWS).map(([key, { name }]) => (
          <a key={key} className={key === view ? 'on' : ''} onClick={() => setQuery(key === 'levels' ? { tab: 'buildings' } : { tab: 'buildings', view: key })}>
            {name}
          </a>
        ))}
      </div>
      <div className="lead">
        {shapes && (
          <span className="choice">
            {Object.keys(shapes).map((name) => (
              <a key={name} className={name === by ? 'on' : ''} onClick={() => change('by', name)}>
                by {name}
              </a>
            ))}
          </span>
        )}
        {view === 'money' && (
          <span className="choice">
            {figures.current.map((name) => (
              <a key={name} className={name === figure ? 'on' : ''} onClick={() => change('figure', name)}>
                {label(name)}
              </a>
            ))}
          </span>
        )}
        <input type="search" placeholder="filter" value={words} onChange={(event) => setWords(event.target.value)} />
      </div>
      <Waiting loaded={found}>
        {() =>
          view === 'methods' ? (
            <Spans key={view} run={run} dates={kept!.dates} lines={methods(kept!)} heads={['type', 'method group']} widths={[200, 190]} twist={1} counted start={0} />
          ) : view === 'queue' ? (
            <Spans key={view} run={run} dates={kept!.dates} lines={queued(kept!)} heads={['funder', 'type', 'state']} widths={[100, 210, 200]} twist={null} counted={false} start="first" />
          ) : (
            <Matrix key={`${view} ${by}`} run={run} found={kept!} shape={shapes![by]} show={view === 'money' ? compact : view === 'unstaffed' ? tenths : whole} />
          )
        }
      </Waiting>
    </>
  )
}
