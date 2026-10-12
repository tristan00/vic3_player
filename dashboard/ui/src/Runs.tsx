import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useApi } from './api'
import { Buildings } from './Buildings'
import { Lines } from './charts'
import { PALETTE, heading, label, num, time } from './format'
import { Facts, Grid, Panel, Pill, Waiting, type Col } from './Grid'

export const stateColumn: Col = { name: 'state', render: (row) => <Pill value={row.state ?? 'no end'} tone={row.tone} /> }

export function runColumns(found: any): Col[] {
  return [
    { name: 'run', kind: 'run' },
    stateColumn,
    { name: 'started', kind: 'time' },
    { name: 'minutes', kind: 'num' },
    { name: 'game_years', label: 'game years', kind: 'num' },
    { name: 'country', kind: 'name' },
    { name: 'world', kind: 'world' },
    { name: 'initializer', kind: 'name' },
    { name: 'picker', kind: 'name' },
    { name: 'attempted', kind: 'int', group: 'actions' },
    ...found.statuses.map((status: string) => ({ name: status, kind: 'int', group: 'actions' })),
    { name: 'unverified', kind: 'int', group: 'actions' },
    { name: 'score', kind: 'num' },
  ]
}

export function Runs() {
  const runs = useApi('/api/runs', 15000)
  return (
    <div className="page">
      <h1>Runs</h1>
      <Waiting loaded={runs}>{() => <Grid sync fold rows={runs.data.rows} columns={runColumns(runs.data)} sort={{ name: 'run', desc: true }} facets={['state', 'country', 'initializer', 'picker']} />}</Waiting>
    </div>
  )
}

const TABS = ['overview', 'buildings', 'actions', 'selection', 'score', 'state', 'timing', 'record']

function Score({ found }: { found: any }) {
  const result = found.breakdown
  if (!result || !result.parts) return <div className="lead">{found.row.not_scored ? `not scored: ${label(found.row.not_scored)}` : 'not scored'}</div>
  const names = [...new Set(result.parts.flatMap((part: any) => Object.keys(part)))].filter((name) => name !== 'component') as string[]
  return (
    <Panel title={`Score ${num(result.score)}`} extra={`${found.objective.name} · ${num(result.years)} years · from snapshot ${result.baseline_seq}`}>
      <Grid search={false} rows={result.parts} columns={[{ name: 'component', kind: 'name' }, ...names.map((name) => ({ name, kind: 'num' }))]} />
    </Panel>
  )
}

function Through({ run, live }: { run: number; live: boolean }) {
  const series = useApi(`/api/runs/${run}/series`, live ? 15000 : 0)
  return (
    <Waiting loaded={series}>
      {() => (
        <div className="columns two">
          <Panel title="Treasury">
            <Lines
              zero
              series={[
                { name: 'balance', color: PALETTE[0], heavy: true, points: series.data.treasury.map((point: any) => [point.year, point.money - point.principal]) },
                ...(series.data.treasury.some((point: any) => point.principal > 0) ? [{ name: 'credit limit', color: PALETTE[7], points: series.data.treasury.map((point: any) => [point.year, -point.credit] as [number, number]) }] : []),
              ]}
            />
          </Panel>
          {Object.entries(series.data.components).map(([component, points]: [string, any]) => (
            <Panel key={component} title={heading(component)}>
              <Lines series={[{ name: component, color: PALETTE[0], points }]} />
            </Panel>
          ))}
        </div>
      )}
    </Waiting>
  )
}

function ActionLog({ run, live }: { run: number; live: boolean }) {
  const actions = useApi(`/api/runs/${run}/actions`, live ? 10000 : 0)
  return (
    <Waiting loaded={actions}>
      {() => {
        const rows: any[] = actions.data.rows
        const advisors = [...new Set(rows.filter((row) => row.act).map((row) => String(row.advisor)))]
        return (
          <Grid
            sync
            run={run}
            rows={rows}
            facets={['advisor', 'status']}
            picked={{ advisor: advisors }}
            sort={{ name: 'n', desc: false }}
            columns={[{ name: 'n', kind: 'int' }, { name: 'turn', kind: 'int' }, { name: 'date' }, { name: 'lever', kind: 'lever' }, { name: 'act', kind: 'act' }, { name: 'command', kind: 'name' }, { name: 'params', label: 'parameters', kind: 'params' }, { name: 'status', render: (row) => <><Pill value={row.status} tone={row.status === 'done' ? 'good' : 'warn'} />{row.unverified && <small> unverified</small>}</> }, { name: 'detail', label: 'response', kind: 'text' }, { name: 'ms', kind: 'ms' }, { name: 'before_seq', label: 'snapshot', render: (row) => <Link to={`/runs/${run}?tab=state&seq=${row.before_seq}`}>{row.before_seq}</Link> }]}
          />
        )
      }}
    </Waiting>
  )
}

function Selection({ run, row }: { run: number; row: any }) {
  const selection = useApi(`/api/runs/${run}/selection`)
  const [query, setQuery] = useSearchParams()
  const seq = query.get('pause')
  const candidates = useApi(seq ? `/api/runs/${run}/candidates/${seq}` : null)
  return (
    <Waiting loaded={selection}>
      {() => {
        const { weights, records, pauses } = selection.data
        const top = Math.max(...weights.map((weight: any) => weight.weight), 0)
        return (
          <>
            <Facts items={[['initializer', label(row.initializer ?? '')], ['picker', label(row.picker)], ['candidates', row.candidates]]} />
            {records
              .filter((record: any) => record.row)
              .map((record: any) => (
                <Panel key={record.table} title={heading(record.table)}>
                  <Facts items={Object.entries(record.row).filter(([, value]) => value !== null).map(([name, value]) => [name, typeof value === 'number' ? num(value) : String(value)])} />
                </Panel>
              ))}
            {pauses.length > 0 && (
              <Panel title="Pauses">
                <Grid rows={pauses} page={30} columns={[{ name: 'seq', label: 'snapshot', render: (pause) => <a onClick={() => setQuery({ tab: 'selection', pause: String(pause.seq) })}>{pause.seq}</a> }, { name: 'date' }, { name: 'candidates', kind: 'int' }, { name: 'distinct_predictions', kind: 'int' }, { name: 'lowest', kind: 'num' }, { name: 'mean', kind: 'num' }, { name: 'highest', kind: 'num' }, { name: 'chosen', label: 'chosen', kind: 'num' }, { name: 'chosen_actions', kind: 'int' }]} />
              </Panel>
            )}
            {seq && (
              <Panel title={`Candidates, snapshot ${seq}`}>
                <Waiting loaded={candidates}>{() => <Grid rows={candidates.data.rows} columns={[{ name: 'candidate', kind: 'int' }, { name: 'predicted_change', label: 'predicted', kind: 'num' }, { name: 'chosen', kind: 'bool' }, { name: 'actions', kind: 'int' }, { name: 'acts', label: 'acts', kind: 'text' }]} />}</Waiting>
              </Panel>
            )}
            <div className="columns two">
              <Panel title="Lever weights">
                <Grid rows={weights.map((weight: any) => ({ ...weight, relative: top && weight.weight !== null ? weight.weight / top : null, done_share: weight.attempted ? weight.done / weight.attempted : null }))} page={40} sort={{ name: 'weight', desc: true }} columns={[{ name: 'lever', kind: 'lever' }, { name: 'weight', kind: 'num' }, { name: 'relative', label: 'relative', kind: 'share' }, { name: 'centre', kind: 'num' }, { name: 'attempted', kind: 'int' }, { name: 'done', kind: 'int' }, { name: 'done_share', label: 'done share', kind: 'share' }]} />
              </Panel>
              <Panel title="Records">
                <Grid rows={records} search={false} page={40} sort={{ name: 'rows', desc: true }} columns={[{ name: 'table', render: (record) => <Link to={`/runs/${run}/tables/${record.table}?at=false`}>{label(record.table)}</Link> }, { name: 'rows', kind: 'int' }]} />
              </Panel>
            </div>
          </>
        )
      }}
    </Waiting>
  )
}

function State({ run, player, country, snapshots }: { run: number; player: number; country: string; snapshots: any[] }) {
  const tables = useApi('/api/tables')
  const [query, setQuery] = useSearchParams()
  const last = snapshots.length ? snapshots[snapshots.length - 1].seq : 0
  const seq = Number(query.get('seq') ?? last)
  return (
    <>
      <div className="lead">
        <label>
          snapshot{' '}
          <select value={seq} onChange={(event) => setQuery({ tab: 'state', seq: event.target.value })}>
            {snapshots.map((snapshot) => (
              <option key={snapshot.seq} value={snapshot.seq}>
                {snapshot.seq} · {snapshot.date} · {label(snapshot.phase)}
              </option>
            ))}
          </select>
        </label>
        <Link to={`/runs/${run}/e/country/${player}?seq=${seq}`}>country {label(country)}</Link>
        <Link to={`/tables?run=${run}`}>tables</Link>
      </div>
      <Waiting loaded={tables}>
        {() => (
          <div className="lead kinds">
            {tables.data.rows
              .filter((row: any) => row.kind === 'history')
              .map((row: any) => (
                <Link key={row.table} to={`/runs/${run}/tables/${row.table}?seq=${seq}`}>
                  {label(row.owner)}
                </Link>
              ))}
          </div>
        )}
      </Waiting>
      <Grid rows={snapshots} page={30} search={false} sort={{ name: 'seq', desc: true }} columns={[{ name: 'seq', label: 'snapshot', render: (snapshot) => <a onClick={() => setQuery({ tab: 'state', seq: String(snapshot.seq) })}>{snapshot.seq}</a> }, { name: 'phase', kind: 'name' }, { name: 'date' }, { name: 'taken', kind: 'time' }, { name: 'read_ms', label: 'read ms', kind: 'num' }]} />
    </>
  )
}

function Timing({ run }: { run: number }) {
  const timing = useApi(`/api/runs/${run}/timing`)
  return (
    <Waiting loaded={timing}>
      {() => {
        const top = Math.max(...timing.data.rows.map((row: any) => row.self_ms), 0)
        return <Grid rows={timing.data.rows.map((row: any) => ({ ...row, relative: top ? row.self_ms / top : null }))} sort={{ name: 'self_ms', desc: true }} columns={[{ name: 'span', kind: 'text' }, { name: 'calls', kind: 'int' }, { name: 'errors', kind: 'int' }, { name: 'self_ms', label: 'self ms', kind: 'num' }, { name: 'relative', label: 'relative', kind: 'share' }, { name: 'total_ms', label: 'total ms', kind: 'num' }, { name: 'p50_ms', label: 'p50 ms', kind: 'num' }, { name: 'p95_ms', label: 'p95 ms', kind: 'num' }, { name: 'p99_ms', label: 'p99 ms', kind: 'num' }, { name: 'max_ms', label: 'max ms', kind: 'num' }]} />
      }}
    </Waiting>
  )
}

function shown(name: string, value: any) {
  if (typeof value === 'string' && /^\d{4}-\d\d-\d\dT/.test(value)) return time(value)
  return typeof value === 'number' && !name.endsWith('seed') && !name.endsWith('_id') ? num(value) : String(value)
}

export function Run() {
  const run = Number(useParams().run)
  const [query, setQuery] = useSearchParams()
  const tab = TABS.includes(query.get('tab') ?? '') ? query.get('tab')! : 'overview'
  const detail = useApi(Number.isInteger(run) ? `/api/runs/${run}` : null, 5000)
  if (!Number.isInteger(run)) return <div className="page"><div className="problem">no run</div></div>
  return (
    <div className="page">
      <Waiting loaded={detail}>
        {() => {
          const found = detail.data
          const row = found.row
          const live = row.state === 'running'
          return (
            <>
              <h1>
                Run {run} <Pill value={row.state ?? 'no end'} tone={row.tone} />
                <span className="extra">
                  {found.previous && <Link to={`/runs/${found.previous}`}>← run {found.previous}</Link>}
                  {found.next && <Link to={`/runs/${found.next}`}>run {found.next} →</Link>}
                </span>
              </h1>
              <Facts
                items={[
                  ['country', <Link to={`/runs/${run}/e/country/${found.player}`}>{label(row.country)}</Link>],
                  ['world', <Link to={`/worlds/${row.world}`}>{row.world_file}</Link>],
                  ['started', time(row.started)],
                  ['minutes', num(row.minutes)],
                  ['game years', row.game_years === null ? '' : `${num(row.game_years)}, to ${row.last_date}`],
                  ['score', row.score === null ? (row.not_scored ? label(row.not_scored) : '—') : num(row.score)],
                  ...(row.end_detail ? [['end detail', row.end_detail] as [string, string]] : []),
                ]}
              />
              <div className="tabs">
                {TABS.map((name) => (
                  <a key={name} className={name === tab ? 'on' : ''} onClick={() => setQuery(name === 'overview' ? {} : { tab: name })}>
                    {name}
                  </a>
                ))}
              </div>
              {tab === 'overview' && <Through run={run} live={live} />}
              {tab === 'buildings' && <Buildings run={run} live={live} />}
              {tab === 'actions' && <ActionLog run={run} live={live} />}
              {tab === 'selection' && <Selection run={run} row={row} />}
              {tab === 'score' && <Score found={found} />}
              {tab === 'state' && <State run={run} player={found.player} country={row.country} snapshots={found.snapshots} />}
              {tab === 'timing' && <Timing run={run} />}
              {tab === 'record' && <Facts items={Object.entries(found.record).filter(([, value]) => value !== null).map(([name, value]) => [name, shown(name, value)])} />}
            </>
          )
        }}
      </Waiting>
    </div>
  )
}
