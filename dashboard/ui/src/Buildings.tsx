import { useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi } from './api'
import { Lines } from './charts'
import { PALETTE, label, num } from './format'
import { Facts, Grid, Panel, type Col } from './Grid'

const DIMENSIONS = ['type', 'location', 'production_method']
const SHOWN = 6
const OTHER = '#8a93a3'

export function Buildings({ run, live }: { run: number; live: boolean }) {
  const [query, setQuery] = useSearchParams()
  const picked = (query.get('by') ?? 'type').split(',').filter((name) => DIMENSIONS.includes(name))
  const by = picked.length ? picked : ['type']
  const asked = new URLSearchParams(by.map((name) => ['by', name]))
  DIMENSIONS.forEach((name) => query.get(name) && asked.set(name, query.get(name)!))
  const found = useApi(`/api/runs/${run}/buildings?${asked}`, live ? 15000 : 0)
  const kept = useRef<any>(null)
  if (found.data) kept.current = found.data
  const data = found.data ?? kept.current
  const change = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(query)
    next.set('tab', 'buildings')
    Object.entries(changes).forEach(([name, value]) => (value ? next.set(name, value) : next.delete(name)))
    setQuery(next)
  }
  const toggle = (name: string) => {
    const next = DIMENSIONS.filter((dimension) => (dimension === name) !== by.includes(dimension))
    if (next.length) change({ by: next.join(',') === 'type' ? null : next.join(',') })
  }
  if (!data) return found.error ? <div className="problem">{found.error}</div> : <div className="waiting">loading</div>
  const split: string[] = data.by
  const years: number[] = data.years
  const last = years.length - 1
  const named = (row: any) => split.map((name) => (name === 'location' ? row.location.label : row[name])).join(' · ')
  const rows: any[] = data.rows.map((row: any) => ({ ...row, name: named(row), start: row.levels[0], end: row.levels[last], change: row.levels[last] - row.levels[0], peak: Math.max(...row.levels), share: data.total[last] ? row.levels[last] / data.total[last] : null }))
  const ranked = [...rows].sort((a, b) => b.peak - a.peak || a.name.localeCompare(b.name))
  const shown = ranked.slice(0, SHOWN).sort((a, b) => a.name.localeCompare(b.name))
  const rest = ranked.slice(SHOWN)
  const series = [
    ...shown.map((row, index) => ({ name: row.name, color: PALETTE[index], points: years.map((year, at) => [year, row.levels[at]] as [number, number]) })),
    ...(rest.length ? [{ name: `${rest.length} others`, color: OTHER, points: years.map((year, at) => [year, rest.reduce((sum, row) => sum + row.levels[at], 0)] as [number, number]) }] : []),
  ]
  const narrowed = DIMENSIONS.filter((name) => query.get(name)).map((name) => (name === 'location' ? (data.options.location.find((option: any) => String(option.id) === query.get(name))?.label ?? query.get(name)) : label(query.get(name)!)))
  const columns: Col[] = [
    ...split.map((name) => (name === 'location' ? { name: 'location', kind: 'entity:state' } : { name, label: label(name), kind: 'name' })),
    { name: 'start', kind: 'int' },
    { name: 'end', kind: 'int' },
    { name: 'change', kind: 'int' },
    { name: 'peak', kind: 'int' },
    { name: 'share', label: split.includes('production_method') ? 'share of levels using it' : 'share of levels', kind: 'share' },
  ]
  return (
    <div style={{ opacity: found.loading ? 0.6 : 1 }}>
      {found.error && <div className="problem">stale: {found.error}</div>}
      <div className="lead">
        <span>split by</span>
        <span className="choice">
          {DIMENSIONS.map((name) => (
            <a key={name} className={by.includes(name) ? 'on' : ''} onClick={() => toggle(name)}>
              {label(name)}
            </a>
          ))}
        </span>
        {DIMENSIONS.map((name) => (
          <label key={name}>
            {label(name)}{' '}
            <select value={query.get(name) ?? ''} onChange={(event) => change({ [name]: event.target.value || null })}>
              <option value="">all</option>
              {data.options[name].map((option: any) =>
                name === 'location' ? (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ) : (
                  <option key={option} value={option}>
                    {label(option)}
                  </option>
                ),
              )}
            </select>
          </label>
        ))}
      </div>
      <Facts items={[['levels at start', num(data.total[0])], [`levels at ${data.dates[last]}`, num(data.total[last])], ['change', num(data.total[last] - data.total[0])], ['combinations', rows.length]]} />
      <Panel title={`Building levels by ${split.map(label).join(' and ')}`} extra={[narrowed.length ? `only ${narrowed.join(', ')}` : '', rest.length ? `the ${SHOWN} highest at their peak, the rest summed` : ''].filter(Boolean).join(' · ') || undefined}>
        <Lines zero step height={280} series={series} />
      </Panel>
      <Grid run={run} rows={rows} sort={{ name: 'end', desc: true }} columns={columns} />
    </div>
  )
}
