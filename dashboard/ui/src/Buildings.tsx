import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi } from './api'
import { Lines, useWidth } from './charts'
import { PALETTE, label, num } from './format'
import { Entity, Grid, Panel, Waiting, type Col } from './Grid'

type Span = [number, number, number, number, number | null]
type Found = {
  dates: string[]
  years: number[]
  types: Record<string, string>
  states: Record<string, string | null>
  countries: Record<string, string | null>
  methods: { group: string; method: string }[]
  buildings: { id: number; type: string; spans: Span[] }[]
  uses: [number, number, number, number][]
}
type Chosen = { not: boolean; values: string[] }
type Option = { key: string; text: string }

const DIMENSIONS = ['country', 'type', 'state', 'method']
const TITLES: Record<string, string> = { country: 'country', type: 'type', state: 'state', method: 'production method' }
const ALL: Chosen = { not: true, values: [] }
const WIDEST = 60
const NARROWEST = 4

function chosen(query: URLSearchParams, name: string, first: Chosen): Chosen {
  if (query.has(`not.${name}`)) return { not: true, values: query.getAll(`not.${name}`).filter(Boolean) }
  if (query.has(name)) return { not: false, values: query.getAll(name).filter(Boolean) }
  return first
}

function dated(date: string) {
  return date.endsWith('-01-01') ? date.slice(0, 4) : date.endsWith('-01') ? date.slice(0, 7) : date
}

function pivot(found: Found, by: string[], picked: Record<string, Chosen>, shown: number[]) {
  const size = found.dates.length
  const ok = (name: string, key: string) => picked[name].values.includes(key) !== picked[name].not
  const keyed = found.methods.map((entry) => `${entry.group}|${entry.method}`)
  const wanted = keyed.map((key) => ok('method', key))
  const used: [number, number, number][][] = found.buildings.map(() => [])
  for (const [building, method, from, to] of found.uses) used[building].push([method, from, to])
  const split = by.includes('method')
  const narrowed = wanted.includes(false)
  const seen: Record<string, Set<string>> = Object.fromEntries(DIMENSIONS.map((name) => [name, new Set(picked[name].values)]))
  const rows = new Map<string, any>()
  found.buildings.forEach((building, position) => {
    const typed = ok('type', building.type)
    const mask = narrowed ? new Uint8Array(size) : null
    if (mask) for (const [method, from, to] of used[position]) if (wanted[method]) mask.fill(1, from, to)
    for (const [from, to, levels, state, country] of building.spans) {
      const owned = ok('country', String(country))
      const placed = ok('state', String(state))
      const live = !mask || mask.subarray(from, to).includes(1)
      if (typed && placed && live) seen.country.add(String(country))
      if (owned && placed && live) seen.type.add(building.type)
      if (owned && typed && live) seen.state.add(String(state))
      if (!owned || !placed || !typed) continue
      const row = (method: number | null) => {
        const key = by.map((name) => (name === 'country' ? country : name === 'type' ? building.type : name === 'state' ? state : keyed[method!])).join('\u0001')
        if (!rows.has(key))
          rows.set(key, {
            country: found.countries[String(country)] ?? 'none',
            countryId: country,
            type: found.types[building.type],
            typeKey: building.type,
            state: found.states[String(state)] ?? `state ${state}`,
            stateId: state,
            group: method === null ? null : found.methods[method].group,
            method: method === null ? null : found.methods[method].method,
            methodKey: method === null ? null : keyed[method],
            building: building.id,
            until: 0,
            values: new Array(size).fill(0),
          })
        const entry = rows.get(key)
        if (to > entry.until) {
          entry.until = to
          entry.building = building.id
        }
        return entry.values as number[]
      }
      for (const [method, start, end] of used[position]) {
        const low = Math.max(from, start)
        const high = Math.min(to, end)
        if (low >= high) continue
        seen.method.add(keyed[method])
        if (!split || !wanted[method]) continue
        const values = row(method)
        for (let day = low; day < high; day += 1) values[day] += levels
      }
      if (!split && live) {
        const values = row(null)
        for (let day = from; day < to; day += 1) if (!mask || mask[day]) values[day] += levels
      }
    }
  })
  const texts: Record<string, (key: string) => string> = {
    country: (key) => (key === 'null' ? 'none' : `${found.countries[key] ?? 'country'} ${key}`),
    type: (key) => found.types[key] ?? key,
    state: (key) => `${found.states[key] ?? 'state'} ${key}`,
    method: (key) => key.replace('|', ' · '),
  }
  const options: Record<string, Option[]> = Object.fromEntries(DIMENSIONS.map((name) => [name, [...seen[name]].map((key) => ({ key, text: texts[name](key) })).sort((a, b) => a.text.localeCompare(b.text))]))
  const part = (entry: any, name: string) => (name === 'method' ? `${entry.group}: ${entry.method}` : name === 'state' ? texts.state(String(entry.stateId)) : name === 'country' ? texts.country(String(entry.countryId)) : entry.type)
  const listed = [...rows.values()].filter((entry) => shown.some((day) => entry.values[day])).map((entry) => ({ ...entry, order: by.map((name) => part(entry, name)), peak: Math.max(...entry.values) }))
  listed.sort((a, b) => a.order.map((text: string, index: number) => text.localeCompare(b.order[index])).find((result: number) => result !== 0) ?? 0)
  const top = [...listed].sort((a, b) => b.peak - a.peak).slice(0, PALETTE.length)
  const differing = by.filter((name) => new Set(top.map((entry) => part(entry, name))).size > 1)
  top.forEach((entry, rank) => {
    entry.color = PALETTE[rank]
    entry.name = (differing.length ? differing : by).map((name) => part(entry, name)).join(' · ') || 'all'
  })
  return { rows: listed, top, options }
}

function Pick({ name, options, picked, change }: { name: string; options: Option[]; picked: Chosen; change: (next: Chosen) => void }) {
  const box = useRef<HTMLDetailsElement>(null)
  const [text, setText] = useState('')
  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) box.current.open = false
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const on = (key: string) => picked.values.includes(key) !== picked.not
  const kept = options.filter((option) => on(option.key))
  const every = kept.length === options.length
  return (
    <details ref={box} className={every ? 'pick' : 'pick on'}>
      <summary>
        {name} <b>{every ? 'all' : kept.length === 1 ? label(kept[0].text) : `${kept.length} of ${options.length}`}</b>
      </summary>
      <div className="menu">
        <div className="menu-tools">
          {options.length > 8 && <input type="search" placeholder="find" value={text} onChange={(event) => setText(event.target.value)} />}
          <a onClick={() => change(ALL)}>all</a>
        </div>
        {options
          .filter((option) => option.text.toLowerCase().includes(text.toLowerCase()))
          .map((option) => (
            <div key={option.key} className="option">
              <label>
                <input type="checkbox" checked={on(option.key)} onChange={() => change({ not: picked.not, values: picked.values.includes(option.key) ? picked.values.filter((value) => value !== option.key) : [...picked.values, option.key] })} />
                {label(option.text)}
              </label>
              <a onClick={() => change({ not: false, values: [option.key] })}>only</a>
            </div>
          ))}
      </div>
    </details>
  )
}

function Levels({ run, player, found }: { run: number; player: number; found: Found }) {
  const [query, setQuery] = useSearchParams()
  const first: Record<string, Chosen> = { country: { not: false, values: [String(player)] }, type: ALL, state: ALL, method: ALL }
  const by = query.has('by') ? DIMENSIONS.filter((name) => query.get('by')!.split(',').includes(name)) : ['type']
  const picked = Object.fromEntries(DIMENSIONS.map((name) => [name, chosen(query, name, first[name])]))
  const every = query.get('every') === 'date' ? 'date' : 'year'
  const days = found.dates.map((_, index) => index).filter((index) => every === 'date' || index === 0 || index === found.dates.length - 1 || found.dates[index].slice(0, 4) !== found.dates[index - 1].slice(0, 4))
  const [box, width] = useWidth()
  const [fitted, setFitted] = useState({ scope: '', count: WIDEST })
  const scope = `${width} ${[...query].filter(([name]) => name !== 'from')}`
  const count = fitted.scope === scope ? fitted.count : WIDEST
  const from = Math.max(0, Math.min(Number(query.get('from')) || 0, days.length - count))
  const shown = days.slice(from, from + count)
  const { rows, top, options } = useMemo(() => pivot(found, by, picked, shown), [found, query.toString(), count])
  useLayoutEffect(() => {
    const table = box.current?.querySelector('table')
    const column = table?.querySelector<HTMLElement>('thead tr:last-child th.right')
    if (!table || !column) return
    const over = table.offsetWidth - box.current!.clientWidth
    if (over > 0 && count > NARROWEST) setFitted({ scope, count: Math.max(NARROWEST, count - Math.ceil(over / column.offsetWidth)) })
  })
  const change = (edit: (params: URLSearchParams) => void) => {
    const params = new URLSearchParams(query)
    edit(params)
    setQuery(params, { replace: true })
  }
  const split = (name: string) => {
    const next = DIMENSIONS.filter((other) => (other === name) !== by.includes(other)).join(',')
    change((params) => (next === 'type' ? params.delete('by') : params.set('by', next)))
  }
  const write = (name: string, next: Chosen) =>
    change((params) => {
      params.delete(name)
      params.delete(`not.${name}`)
      const same = next.not === first[name].not && next.values.length === first[name].values.length && next.values.every((value) => first[name].values.includes(value))
      if (!same) (next.values.length ? next.values : ['']).forEach((value) => params.append(next.not ? `not.${name}` : name, value))
    })
  const only = (name: string, key: (row: any) => string, inside: (row: any) => ReactNode) => (row: any) => (
    <span className="filterable">
      {inside(row)}
      <a className="only" title="only" onClick={() => write(name, { not: false, values: [key(row)] })}>
        ▾
      </a>
    </span>
  )
  const single = by.includes('type') && by.includes('state')
  const labels: Record<string, Col[]> = {
    country: [{ name: 'country', render: only('country', (row) => String(row.countryId), (row) => (row.countryId === null ? row.country : <Entity run={run} kind="country" id={row.countryId} name={row.country} />)) }],
    type: [{ name: 'type', render: only('type', (row) => row.typeKey, (row) => (single ? <Entity run={run} kind="building" id={row.building} name={row.type} /> : label(row.type))) }],
    state: [{ name: 'state', render: only('state', (row) => String(row.stateId), (row) => <Entity run={run} kind="state" id={row.stateId} name={row.state} />) }],
    method: [
      { name: 'group', label: 'method group', kind: 'name' },
      { name: 'method', label: 'production method', render: only('method', (row) => row.methodKey, (row) => label(row.method)) },
    ],
  }
  const columns: Col[] = [
    { name: 'color', label: '', render: (row) => row.color && <i className="key" style={{ background: row.color }} /> },
    ...by.flatMap((name) => labels[name]),
    ...shown.map((index, position) => ({
      name: `d${index}`,
      label: every === 'date' ? found.dates[index].slice(5).replace(/-01$/, '') : dated(found.dates[index]),
      group: every === 'date' ? found.dates[index].slice(0, 4) : undefined,
      kind: 'int',
      render: (row: any) => <span className={position > 0 && row.values[index] === row.values[shown[position - 1]] ? 'same' : ''}>{row.values[index] ? num(row.values[index]) : ''}</span>,
    })),
  ]
  return (
    <>
      <div className="lead">
        <span>by</span>
        <span className="choice">
          {DIMENSIONS.map((name) => (
            <a key={name} className={by.includes(name) ? 'on' : ''} onClick={() => split(name)}>
              {TITLES[name]}
            </a>
          ))}
        </span>
        {DIMENSIONS.map((name) => (
          <Pick key={name} name={TITLES[name]} options={options[name]} picked={picked[name]} change={(next) => write(name, next)} />
        ))}
        <span>columns</span>
        <span className="choice">
          {['year', 'date'].map((name) => (
            <a
              key={name}
              className={every === name ? 'on' : ''}
              onClick={() =>
                change((params) => {
                  params.delete('from')
                  name === 'year' ? params.delete('every') : params.set('every', name)
                })
              }
            >
              {name}s
            </a>
          ))}
        </span>
        {days.length > count && (
          <>
            <button disabled={from === 0} onClick={() => change((params) => params.set('from', String(Math.max(0, from - count))))}>
              earlier
            </button>
            <button disabled={from + count >= days.length} onClick={() => change((params) => params.set('from', String(from + count)))}>
              later
            </button>
          </>
        )}
      </div>
      <Panel title="Levels" extra={rows.length > top.length ? `${top.length} highest of ${num(rows.length)}` : undefined}>
        <Lines zero step height={260} series={top.map((row) => ({ name: row.name, color: row.color, points: found.years.map((year, index) => [year, row.values[index]] as [number, number]) }))} />
      </Panel>
      <div ref={box} className="levels">
        <Grid sync rows={rows.map((row) => ({ ...row, ...Object.fromEntries(shown.map((index) => [`d${index}`, row.values[index]])) }))} columns={columns} />
      </div>
    </>
  )
}

export function Buildings({ run, player, live }: { run: number; player: number; live: boolean }) {
  const found = useApi<Found>(`/api/runs/${run}/buildings`, live ? 15000 : 0)
  return <Waiting loaded={found}>{() => <Levels run={run} player={player} found={found.data!} />}</Waiting>
}
