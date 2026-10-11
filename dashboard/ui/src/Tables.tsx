import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useApi } from './api'
import { Multiples } from './charts'
import { heading, label } from './format'
import { AsOf, Cell, Grid, Panel, Waiting, type Col } from './Grid'

function Snapshot({ run, seq, change }: { run: number; seq: number | null; change: (seq: string) => void }) {
  const detail = useApi(`/api/runs/${run}`)
  const snapshots: any[] = detail.data?.snapshots ?? []
  return (
    <select value={seq ?? (snapshots.length ? snapshots[snapshots.length - 1].seq : '')} onChange={(event) => change(event.target.value)}>
      {snapshots.map((snapshot) => (
        <option key={snapshot.seq} value={snapshot.seq}>
          {snapshot.seq} · {snapshot.date} · {label(snapshot.phase)}
        </option>
      ))}
    </select>
  )
}

export function Tables() {
  const tables = useApi('/api/tables')
  const runs = useApi('/api/runs')
  const [query, setQuery] = useSearchParams()
  const latest = runs.data ? Math.max(...runs.data.rows.map((row: any) => row.run)) : null
  const run = query.get('run') ? Number(query.get('run')) : latest
  return (
    <div className="page">
      <h1>Tables</h1>
      <div className="lead">
        <label>
          run{' '}
          <select value={run ?? ''} onChange={(event) => setQuery({ run: event.target.value })}>
            {(runs.data?.rows ?? [])
              .map((row: any) => row.run)
              .sort((a: number, b: number) => b - a)
              .map((id: number) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
          </select>
        </label>
      </div>
      <Waiting loaded={tables}>
        {() => (
          <Grid
            sync
            rows={tables.data.rows}
            sort={{ name: 'table' }}
            facets={['kind', 'scope', 'per_run']}
            columns={[
              { name: 'table', render: (row) => <Link to={row.per_run ? `/runs/${run}/tables/${row.table}` : `/tables/${row.table}`}>{label(row.table)}</Link> },
              { name: 'kind' },
              { name: 'owner', kind: 'name' },
              { name: 'scope' },
              { name: 'per_run', label: 'per run', kind: 'bool' },
              { name: 'columns', kind: 'int' },
              { name: 'rows', label: 'rows, estimated', kind: 'int' },
              { name: 'megabytes', kind: 'num' },
            ]}
          />
        )}
      </Waiting>
    </div>
  )
}

function Charts({ run, table, query }: { run: number; table: string; query: string }) {
  const [all, setAll] = useState(false)
  const series = useApi(`/api/runs/${run}/series/${table}?${query}`)
  return (
    <Waiting loaded={series}>
      {() => {
        const columns: string[] = series.data.columns
        return (
          <>
            <Multiples x={series.data.x} axis={series.data.axis} values={series.data.values} columns={all ? columns : columns.slice(0, 12)} />
            {!all && columns.length > 12 && (
              <div className="grid-more">
                <button onClick={() => setAll(true)}>show all {columns.length} columns</button>
              </div>
            )}
          </>
        )
      }}
    </Waiting>
  )
}

export function Table() {
  const params = useParams()
  const run = params.run ? Number(params.run) : null
  const table = params.table!
  const [query, setQuery] = useSearchParams()
  const page = useApi(`${run !== null ? `/api/runs/${run}/tables/${table}` : `/api/tables/${table}`}?${query.toString()}`)
  const set = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(query)
    for (const [name, value] of Object.entries(changes)) value === null ? next.delete(name) : next.set(name, value)
    if (!('offset' in changes)) next.delete('offset')
    setQuery(next)
  }
  return (
    <div className="page">
      <h1>
        {label(table)}
        <span className="extra">
          {run !== null && <Link to={`/runs/${run}?tab=state`}>run {run}</Link>}
          <Link to={run !== null ? `/tables?run=${run}` : '/tables'}>all tables</Link>
        </span>
      </h1>
      <Waiting loaded={page}>
        {() => {
          const found = page.data
          const filters: any[] = found.filters
          const filterable = (column: any) => column.kind === 'name' || column.kind.startsWith('entity:') || found.keys.includes(column.name)
          const columns: Col[] = found.columns.filter((column: any) => !found.empty.includes(column.name)).map((column: any) => ({
            name: column.name,
            kind: column.kind,
            render: filterable(column)
              ? (row: any) => {
                  const value = row[column.name]
                  if (value === null || value === undefined) return null
                  return (
                    <span className="filterable">
                      <Cell column={{ name: column.name, kind: column.kind }} row={row} run={run ?? undefined} />
                      <a className="only" title="filter" onClick={() => set({ [`f.${column.name}`]: String(typeof value === 'object' ? value.id : value) })}>
                        ▾
                      </a>
                    </span>
                  )
                }
              : undefined,
          }))
          const needed = found.keys.filter((key: string) => key !== 'seq' && key !== 'n')
          const chart = run !== null && found.chartable.length > 0 && needed.every((key: string) => filters.some((filter) => filter.column === key))
          return (
            <AsOf.Provider value={found.at && query.get('seq') ? Number(query.get('seq')) : null}>
              <div className="lead">
                <span>
                  {found.kind}
                  {found.owner ? ` of ${label(found.owner)}` : ''}
                </span>
                {run !== null && found.can_at && (
                  <>
                    <span className="choice">
                      <a className={found.at ? 'on' : ''} onClick={() => set({ at: null })}>
                        snapshot
                      </a>
                      <a className={found.at ? '' : 'on'} onClick={() => set({ at: 'false' })}>
                        all rows
                      </a>
                    </span>
                    {found.at && <Snapshot run={run} seq={query.get('seq') ? Number(query.get('seq')) : null} change={(seq) => set({ seq })} />}
                  </>
                )}
                {filters.map((filter) => (
                  <span key={filter.column} className="chip">
                    {label(filter.column)} = {label(String(filter.label))} <a onClick={() => set({ [`f.${filter.column}`]: null })}>×</a>
                  </span>
                ))}
                {found.empty.length > 0 && <span>empty: {found.empty.map((name: string) => label(name)).join(', ')}</span>}
              </div>
              {chart && (
                <Panel title="Over time">
                  <Charts run={run!} table={table} query={filters.map((filter) => `f.${filter.column}=${encodeURIComponent(filter.value)}`).join('&')} />
                </Panel>
              )}
              <Grid rows={found.rows} columns={columns} run={run ?? undefined} remote={{ total: found.total, estimated: found.estimated, offset: found.offset, limit: found.limit, sort: query.get('sort') ?? undefined, desc: query.get('desc') === 'true', change: (next) => set({ ...(next.sort !== undefined ? { sort: next.sort, desc: String(!!next.desc) } : {}), offset: next.offset ? String(next.offset) : null }) }} />
            </AsOf.Provider>
          )
        }}
      </Waiting>
    </div>
  )
}

export function EntityView({ run, kind, id, seq, pick, page }: { run: number; kind: string; id: number; seq: number | null; pick: (seq: string) => void; page: boolean }) {
  const [toggled, setToggled] = useState<Record<string, boolean>>({})
  const [referenced, setReferenced] = useState(false)
  const entity = useApi(`/api/runs/${run}/entities/${kind}/${id}${seq !== null ? `?seq=${seq}` : ''}`)
  const references = useApi(referenced ? `/api/runs/${run}/entities/${kind}/${id}/references` : null)
  return (
    <Waiting loaded={entity}>
      {() => {
        const found = entity.data
        const current = found.current
        const chartable: any[] = found.related.filter((row: any) => row.chart && row.rows > 1).sort((a: any, b: any) => b.rows - a.rows)
        const sampled: string[] = chartable.filter((row) => row.kind === 'sample').map((row) => row.table)
        const dated: string[] = chartable.filter((row) => row.kind !== 'sample').map((row) => row.table)
        const open = (table: string) => toggled[table] ?? false
        const fields = found.columns.filter((column: any) => column.name !== 'seq' && column.name !== 'present')
        const suffix = seq !== null ? `&seq=${seq}` : ''
        const at = seq !== null ? `?seq=${seq}` : ''
        return (
          <AsOf.Provider value={seq}>
            <h1>
              {page ? found.label ? label(found.label) : label(kind) : <Link to={`/runs/${run}/e/${kind}/${id}${at}`}>{found.label ? label(found.label) : label(kind)}</Link>}
              <span className="extra">
                {label(kind)} {id}
                {page && <Link to={`/runs/${run}`}>run {run}</Link>}
                <Link to={`/runs/${run}/tables/${kind}_history${at}`}>all</Link>
              </span>
            </h1>
            <div className="lead">
              <label>
                snapshot <Snapshot run={run} seq={found.seq} change={pick} />
              </label>
              <span>first {found.first_seq}</span>
              {current && <span>changed {current.seq}</span>}
            </div>
            <div className="columns two">
              <Panel title={current ? (current.present ? 'Values' : 'Gone') : 'Not recorded'}>
                {current && current.present && (
                  <table className="attributes">
                    <tbody>
                      {fields
                        .filter((column: any) => current[column.name] !== null)
                        .map((column: any) => (
                          <tr key={column.name}>
                            <th>{label(column.name)}</th>
                            <td>
                              <Cell column={column} row={current} run={run} />
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                )}
              </Panel>
              <Panel title="Tables">
                <Grid
                  rows={found.related.filter((row: any) => row.rows > 0)}
                  search={false}
                  page={60}
                  sort={{ name: 'rows', desc: true }}
                  columns={[
                    { name: 'table', render: (row) => <Link to={`/runs/${run}/tables/${row.table}?f.${kind}=${id}${suffix}`}>{label(row.table)}</Link> },
                    { name: 'kind' },
                    { name: 'rows', kind: 'int' },
                    { name: 'chart', label: 'over time', render: (row) => (dated.includes(row.table) ? <a onClick={() => setToggled({ ...toggled, [row.table]: !open(row.table) })}>{open(row.table) ? 'hide' : 'charts'}</a> : sampled.includes(row.table) ? 'samples' : null) },
                  ]}
                />
              </Panel>
            </div>
            {dated.filter(open).map((table) => (
              <Panel key={table} title={heading(table)}>
                <Charts run={run} table={table} query={`f.${kind}=${id}`} />
              </Panel>
            ))}
            {sampled.length > 0 && (
              <Panel title="Samples">
                <div className="sampled">
                  {sampled.map((table) => (
                    <Charts key={table} run={run} table={table} query={`f.${kind}=${id}`} />
                  ))}
                </div>
              </Panel>
            )}
            <Panel title="Versions">
              <Grid fold rows={found.versions} run={run} search={false} page={20} sort={{ name: 'seq', desc: true }} columns={[{ name: 'seq', kind: 'int' }, { name: 'date' }, ...found.columns.filter((column: any) => column.name !== 'seq')]} />
            </Panel>
            <Panel title="References" extra={!referenced && <a onClick={() => setReferenced(true)}>count</a>}>
              {referenced && <Waiting loaded={references}>{() => <Grid rows={references.data.rows} search={false} page={80} sort={{ name: 'rows', desc: true }} columns={[{ name: 'table', render: (row) => <Link to={`/runs/${run}/tables/${row.table}?f.${row.column}=${id}&at=false`}>{label(row.table)}</Link> }, { name: 'column', kind: 'name' }, { name: 'rows', kind: 'int' }]} />}</Waiting>}
            </Panel>
          </AsOf.Provider>
        )
      }}
    </Waiting>
  )
}

export function Entity() {
  const params = useParams()
  const [query, setQuery] = useSearchParams()
  const run = Number(params.run)
  const id = Number(params.id)
  if (!Number.isInteger(run) || !Number.isInteger(id))
    return (
      <div className="page">
        <div className="problem">no entity</div>
      </div>
    )
  return (
    <div className="page">
      <EntityView key={`${params.kind} ${id}`} run={run} kind={params.kind!} id={id} seq={query.get('seq') ? Number(query.get('seq')) : null} pick={(seq) => setQuery({ seq })} page />
    </div>
  )
}
