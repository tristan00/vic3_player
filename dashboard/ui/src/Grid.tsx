import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Share } from './charts'
import { fraction, label, num, time } from './format'

export type Col = {
  name: string
  label?: string
  kind?: string
  group?: string
  render?: (row: any) => ReactNode
}

export type Remote = { total: number; estimated: boolean; offset: number; limit: number; sort?: string; desc?: boolean; change: (next: { sort?: string; desc?: boolean; offset?: number }) => void }

const RIGHT = new Set(['num', 'int', 'frac', 'share', 'ms'])

export const AsOf = createContext<number | null>(null)

export function Pill({ value, tone = 'plain' }: { value: string; tone?: string }) {
  return <span className={`pill ${tone}`}>{label(value)}</span>
}

export function Entity({ run, kind, id, name }: { run: number; kind: string; id: number; name?: string | null }) {
  const seq = useContext(AsOf)
  return (
    <Link to={`/runs/${run}/e/${kind}/${id}${seq === null ? '' : `?seq=${seq}`}`} className="entity">
      {name ? label(name) : label(kind)} <small>{id}</small>
    </Link>
  )
}

export function Params({ run, params }: { run: number; params: any[] }) {
  return (
    <span className="params">
      {params.map((param) => (
        <span key={param.name}>
          <small>{label(param.name)}</small> {param.entity ? <Entity run={run} kind={param.entity} id={param.value} name={param.label} /> : typeof param.value === 'string' ? label(param.value) : param.value}
        </span>
      ))}
    </span>
  )
}

function guess(value: any) {
  if (typeof value === 'number') return Number.isInteger(value) ? 'int' : 'num'
  if (typeof value === 'boolean') return 'bool'
  return 'text'
}

export function Cell({ column, row, run }: { column: Col; row: any; run?: number }) {
  if (column.render) return <>{column.render(row)}</>
  const value = row[column.name]
  if (value === null || value === undefined) return null
  const kind = column.kind ?? guess(value)
  const scope = run ?? row.run ?? row.run_id
  if (kind.startsWith('entity:')) return <Entity run={scope} kind={kind.slice(7)} id={value.id} name={value.label} />
  switch (kind) {
    case 'run':
      return <Link to={`/runs/${value}`}>{value}</Link>
    case 'state':
      return <Pill value={value} tone={row.tone} />
    case 'status':
      return <Pill value={value} tone={value === 'done' ? 'good' : 'warn'} />
    case 'time':
      return <>{time(value)}</>
    case 'int':
    case 'num':
    case 'ms':
      return <>{num(value)}</>
    case 'frac':
      return <>{fraction(value)}</>
    case 'share':
      return <Share value={value} />
    case 'bool':
      return <span className={value ? 'yes' : 'no'}>{value ? 'yes' : 'no'}</span>
    case 'act':
      return <Link to={`/actions/${encodeURIComponent(value)}`}>{label(value)}</Link>
    case 'lever':
      return <Link to={`/actions?lever=${encodeURIComponent(value)}`}>{label(value)}</Link>
    case 'world':
      return <Link to={`/worlds/${value}`}>{value}</Link>
    case 'params':
      return <Params run={scope} params={value} />
    case 'name':
      return <>{label(String(typeof value === 'object' ? (value.label ?? value.id) : value))}</>
    default:
      return <>{String(value)}</>
  }
}

function sortable(value: any) {
  if (value === null || value === undefined) return null
  if (Array.isArray(value)) return value.length
  if (typeof value === 'object') return value.label ?? value.id
  return value
}

function facetValue(value: any) {
  return String((value !== null && typeof value === 'object' ? (value.label ?? value.id) : value) ?? '')
}

export function Grid({ columns: every, rows, sort, facets = [], picked = {}, search = true, page = 100, run, remote, sync = false, fold = false }: { columns: Col[]; rows: any[]; sort?: { name: string; desc?: boolean }; facets?: string[]; picked?: Record<string, string[]>; search?: boolean; page?: number; run?: number; remote?: Remote; sync?: boolean; fold?: boolean }) {
  const same = useMemo(() => (fold && !remote && rows.length > 1 ? every.slice(1).filter((column) => !column.render && new Set(rows.map((row) => JSON.stringify(row[column.name] ?? null))).size === 1) : []), [every, rows, fold, remote])
  const twins = useMemo(() => {
    const found: [Col, Col][] = []
    if (!fold || remote || rows.length < 2) return found
    const kept = every.filter((column) => !same.includes(column))
    kept.forEach((column, index) => {
      const earlier = kept.slice(0, index).find((other) => !other.render && !column.render && other.kind === column.kind && !found.some(([twin]) => twin === other) && rows.every((row) => JSON.stringify(row[other.name] ?? null) === JSON.stringify(row[column.name] ?? null)))
      if (earlier) found.push([column, earlier])
    })
    return found
  }, [every, rows, fold, remote, same])
  const columns = every.filter((column) => !same.includes(column) && !twins.some(([twin]) => twin === column))
  const [query, setQuery] = useSearchParams()
  const kept = (name: string) => (sync ? query.get(name) : null)
  const [order, setOrder] = useState(() => {
    const found = kept('sort')
    return found ? { name: found.replace(/^-/, ''), desc: found.startsWith('-') } : sort
  })
  const [text, setText] = useState(() => kept('q') ?? '')
  const [chosen, setChosen] = useState<Record<string, string[]>>(() => ({ ...picked, ...Object.fromEntries(facets.filter((name) => kept(`only.${name}`) !== null).map((name) => [name, kept(`only.${name}`)!.split('|').filter(Boolean)])) }))
  const [shown, setShown] = useState(page)
  const write = (name: string, value: string) => {
    if (!sync) return
    setQuery(
      (before) => {
        const next = new URLSearchParams(before)
        if (value) next.set(name, value)
        else next.delete(name)
        return next
      },
      { replace: true },
    )
  }
  const words = text.toLowerCase().replace(/_/g, ' ').split(/\s+/).filter(Boolean)
  const matches = (row: any, except?: string) => {
    for (const [name, values] of Object.entries(chosen)) if (name !== except && values.length && !values.includes(facetValue(row[name]))) return false
    if (!words.length) return true
    const hay = JSON.stringify(row).toLowerCase().replace(/_/g, ' ')
    return words.every((word) => hay.includes(word))
  }
  const choices = useMemo(
    () =>
      facets.map((name) => {
        const counts = new Map<string, number>()
        for (const row of rows) counts.set(facetValue(row[name]), 0)
        for (const row of rows) if (matches(row, name)) counts.set(facetValue(row[name]), counts.get(facetValue(row[name]))! + 1)
        return { name, values: [...counts.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)) }
      }),
    [rows, facets.join(','), text, chosen],
  )
  const filtered = useMemo(() => {
    let found = rows.filter((row) => matches(row))
    if (order && !remote) {
      const sign = order.desc ? -1 : 1
      found = [...found].sort((a, b) => {
        const left = sortable(a[order.name])
        const right = sortable(b[order.name])
        if (left === right) return 0
        if (left === null) return 1
        if (right === null) return -1
        return (left < right ? -1 : 1) * sign
      })
    }
    return found
  }, [rows, text, chosen, order, remote])
  const visible = remote ? filtered : filtered.slice(0, shown)
  const groups = columns.some((column) => column.group)
  const press = (column: Col) => {
    if (remote) return remote.change({ sort: column.name, desc: remote.sort === column.name ? !remote.desc : RIGHT.has(column.kind ?? ''), offset: 0 })
    const next = { name: column.name, desc: order?.name === column.name ? !order.desc : RIGHT.has(column.kind ?? '') }
    setOrder(next)
    write('sort', (next.desc ? '-' : '') + next.name)
  }
  const active = remote ? { name: remote.sort, desc: remote.desc } : order
  const toggle = (name: string, value: string) => {
    const next = chosen[name]?.includes(value) ? chosen[name].filter((other) => other !== value) : [...(chosen[name] ?? []), value]
    setChosen({ ...chosen, [name]: next })
    write(`only.${name}`, next.join('|'))
  }
  const range = remote ? (rows.length ? `${num(remote.offset + 1)}–${num(remote.offset + rows.length)} of ${remote.estimated ? 'about ' : ''}${num(remote.total)} rows` : '0 rows') : filtered.length === rows.length ? `${num(rows.length)} rows` : `${num(filtered.length)} of ${num(rows.length)} rows`
  return (
    <div className="grid">
      {(search || choices.length > 0 || remote) && (
        <div className="grid-tools">
          {search && !remote && (
            <input
              type="search"
              placeholder="filter"
              value={text}
              onChange={(event) => {
                setText(event.target.value)
                write('q', event.target.value)
              }}
            />
          )}
          {choices.map((choice) => (
            <span key={choice.name} className="facet">
              <small>{label(choice.name)}</small>
              {choice.values.map(([value, count]) => (
                <button key={value} className={chosen[choice.name]?.includes(value) ? 'on' : ''} onClick={() => toggle(choice.name, value)}>
                  {value ? label(value) : 'none'} <small>{count}</small>
                </button>
              ))}
            </span>
          ))}
          <span className="count">{range}</span>
          {remote && (
            <>
              <button disabled={remote.offset === 0} onClick={() => remote.change({ offset: Math.max(0, remote.offset - remote.limit) })}>
                previous
              </button>
              <button disabled={remote.estimated ? rows.length < remote.limit : remote.offset + remote.limit >= remote.total} onClick={() => remote.change({ offset: remote.offset + remote.limit })}>
                next
              </button>
            </>
          )}
        </div>
      )}
      {(same.length > 0 || twins.length > 0) && (
        <dl className="facts same">
          {same.length > 0 && <span>constant</span>}
          {same.map((column) => (
            <div key={column.name}>
              <dt>{column.label ?? label(column.name)}</dt>
              <dd>{rows[0][column.name] === null || rows[0][column.name] === undefined ? 'empty' : <Cell column={column} row={rows[0]} run={run} />}</dd>
            </div>
          ))}
          {twins.map(([column, earlier]) => (
            <div key={column.name}>
              <dt>{column.label ?? label(column.name)}</dt>
              <dd>= {earlier.label ?? label(earlier.name)}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="grid-box">
        <table>
          <thead>
            {groups && (
              <tr className="groups">
                {columns.map((column, index) => {
                  if (index > 0 && columns[index - 1].group === column.group) return null
                  let width = 1
                  while (columns[index + width] && columns[index + width].group === column.group) width += 1
                  return (
                    <th key={index} colSpan={width} className={column.group ? 'group' : ''}>
                      {column.group ? label(column.group) : ''}
                    </th>
                  )
                })}
              </tr>
            )}
            <tr>
              {columns.map((column) => (
                <th key={column.name} className={RIGHT.has(column.kind ?? '') ? 'right' : ''} onClick={() => press(column)}>
                  {column.label ?? label(column.name)}
                  {active?.name === column.name && <span className="arrow">{active.desc ? '▼' : '▲'}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, index) => (
              <tr key={index}>
                {columns.map((column) => (
                  <td key={column.name} className={`${RIGHT.has(column.kind ?? '') ? 'right' : ''} ${column.kind === 'text' || column.kind === 'params' ? 'wrap' : ''}`}>
                    <Cell column={column} row={row} run={run} />
                  </td>
                ))}
              </tr>
            ))}
            {!visible.length && (
              <tr>
                <td colSpan={columns.length} className="none">
                  no rows
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {!remote && filtered.length > shown && (
        <div className="grid-more">
          showing {num(shown)} of {num(filtered.length)}
          <button onClick={() => setShown(shown + page * 2)}>show {num(Math.min(page * 2, filtered.length - shown))} more</button>
          <button onClick={() => setShown(filtered.length)}>show all</button>
        </div>
      )}
    </div>
  )
}

export function Facts({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="facts">
      {items.map(([name, value]) => (
        <div key={name}>
          <dt>{label(name)}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Figures({ items }: { items: [string, ReactNode, ReactNode?][] }) {
  return (
    <div className="figures">
      {items.map(([name, value, extra]) => (
        <div key={name}>
          <small>{name}</small>
          <b>{value}</b>
          {extra && <span>{extra}</span>}
        </div>
      ))}
    </div>
  )
}

export function Panel({ title, extra, children }: { title?: ReactNode; extra?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel">
      {(title || extra) && (
        <h2>
          {title}
          {extra && <span className="extra">{extra}</span>}
        </h2>
      )}
      {children}
    </section>
  )
}

export function Waiting({ loaded, children }: { loaded: { data?: any; error?: string; loading: boolean }; children: () => ReactNode }) {
  if (loaded.data !== undefined)
    return (
      <>
        {loaded.error && <div className="problem">stale: {loaded.error}</div>}
        {children()}
      </>
    )
  if (loaded.error) return <div className="problem">{loaded.error}</div>
  return <div className="waiting">loading</div>
}

export function columnsOf(rows: any[], first: Col[] = []): Col[] {
  const taken = new Set(first.map((column) => column.name))
  const names = [...new Set(rows.flatMap((row) => Object.keys(row)))].filter((name) => !taken.has(name))
  return [...first, ...names.map((name) => ({ name, kind: rows.some((row) => typeof row[name] === 'number') ? 'num' : rows.some((row) => typeof row[name] === 'boolean') ? 'bool' : 'name' }))]
}
