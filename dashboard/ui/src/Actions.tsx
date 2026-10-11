import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useApi } from './api'
import { label, num, sum } from './format'
import { Facts, Figures, Grid, Panel, Waiting, type Col } from './Grid'

function outcome(statuses: string[], group?: string): Col[] {
  return [{ name: 'attempted', kind: 'int', group }, ...statuses.map((status) => ({ name: status, kind: 'int', group })), { name: 'unverified', label: 'unverified', kind: 'int', group }, { name: 'done_share', label: 'done share', kind: 'share', group }]
}

function shared(rows: any[]) {
  return rows.map((row) => ({ ...row, done_share: row.attempted ? row.done / row.attempted : null }))
}

function totals(rows: any[], statuses: string[]): [string, string][] {
  return [['attempted', num(sum(rows.map((row) => row.attempted)))], ...statuses.map((status) => [label(status), num(sum(rows.map((row) => row[status])))] as [string, string]), ['unverified', num(sum(rows.map((row) => row.unverified)))]]
}

export function Actions() {
  const [query, setQuery] = useSearchParams()
  const lever = query.get('lever')
  const by = query.get('by') === 'command' ? 'command' : 'act'
  const acts = useApi(by === 'act' ? '/api/acts' : '/api/commands', 30000)
  const choose = (next: string) => setQuery(next === 'act' ? {} : { by: next })
  return (
    <div className="page">
      <h1>
        Actions
        <span className="choice">
          <a className={by === 'act' ? 'on' : ''} onClick={() => choose('act')}>
            acts
          </a>
          <a className={by === 'command' ? 'on' : ''} onClick={() => choose('command')}>
            commands
          </a>
        </span>
        {lever && (
          <span className="extra">
            lever {label(lever)} · <a onClick={() => setQuery({})}>all</a>
          </span>
        )}
      </h1>
      <Waiting loaded={acts}>
        {() => {
          const rows = shared(acts.data.rows.filter((row: any) => !lever || row.lever === lever))
          const statuses: string[] = acts.data.statuses
          const chosen = rows.filter((row) => row.acts?.length)
          if (lever && !rows.length) return <div className="problem">no lever {label(lever)}</div>
          return by === 'act' ? (
            <>
              <Figures items={[['acts', num(rows.length)], ['used', num(rows.filter((row) => row.attempted).length)], ...totals(rows, statuses)]} />
              <Grid key={`act${lever}`} sync rows={rows} sort={{ name: 'attempted', desc: true }} facets={['domain']} columns={[{ name: 'act', kind: 'act' }, { name: 'lever', kind: 'lever' }, { name: 'domain' }, { name: 'commands', label: 'commands', kind: 'text' }, { name: 'runs', kind: 'int' }, ...outcome(statuses, 'outcomes'), { name: 'ms', label: 'median ms', kind: 'num' }]} />
            </>
          ) : (
            <>
              <Figures items={[['commands', num(chosen.length)], ...totals(chosen, statuses)]} />
              <Grid key="command" sync rows={rows} sort={{ name: 'attempted', desc: true }} facets={['advisors']} picked={{ advisors: [...new Set(chosen.map((row) => String(row.advisors)))] }} columns={[{ name: 'command', kind: 'name' }, { name: 'acts', label: 'acts', kind: 'text', render: (row) => row.acts.map((act: string) => <Link key={act} to={`/actions/${encodeURIComponent(act)}`} className="listed">{label(act)}</Link>) }, { name: 'levers', kind: 'text', render: (row) => row.levers.map((name: string) => <Link key={name} to={`/actions?lever=${encodeURIComponent(name)}`} className="listed">{label(name)}</Link>) }, { name: 'runs', kind: 'int' }, ...outcome(statuses, 'outcomes'), { name: 'ms', label: 'median ms', kind: 'num' }]} />
            </>
          )
        }}
      </Waiting>
    </div>
  )
}

export function Levers() {
  const levers = useApi('/api/levers', 30000)
  return (
    <div className="page">
      <h1>Levers</h1>
      <Waiting loaded={levers}>{() => <Grid sync rows={shared(levers.data.rows)} sort={{ name: 'attempted', desc: true }} facets={['domain']} columns={[{ name: 'lever', kind: 'lever' }, { name: 'domain' }, { name: 'acts', kind: 'int' }, ...outcome(levers.data.statuses, 'outcomes'), { name: 'weighted_runs', label: 'runs', kind: 'int', group: 'weight' }, { name: 'weight_min', label: 'lowest', kind: 'num', group: 'weight' }, { name: 'weight_median', label: 'median', kind: 'num', group: 'weight' }, { name: 'weight_max', label: 'highest', kind: 'num', group: 'weight' }]} />}</Waiting>
    </div>
  )
}

export function Act() {
  const name = useParams().name!
  const act = useApi(`/api/acts/${encodeURIComponent(name)}`, 30000)
  return (
    <div className="page">
      <h1>
        {label(name)}
        <span className="extra">
          <Link to="/actions">all</Link>
        </span>
      </h1>
      <Waiting loaded={act}>
        {() => {
          const found = act.data
          const plain = outcome(found.statuses)
          return (
            <>
              <Facts items={[['lever', found.lever ? <Link to={`/actions?lever=${encodeURIComponent(found.lever)}`}>{label(found.lever)}</Link> : ''], ['domain', found.domain ?? ''], ['parameters', found.parameters.map((parameter: any) => (parameter.name === parameter.kind ? label(parameter.name) : `${label(parameter.name)} (${label(parameter.kind)})`)).join(', ')]]} />
              <Figures items={[['runs', num(found.runs.length)], ...totals(found.runs, found.statuses)]} />
              <div className="columns two">
                <Panel title="Commands">
                  <Grid rows={shared(found.commands)} search={false} sort={{ name: 'attempted', desc: true }} columns={[{ name: 'command', kind: 'name' }, ...plain]} />
                </Panel>
                <Panel title="Responses">
                  <Grid rows={found.responses} page={12} search={false} sort={{ name: 'count', desc: true }} columns={[{ name: 'status', kind: 'status' }, { name: 'unverified', kind: 'bool' }, { name: 'detail', label: 'response', kind: 'text' }, { name: 'count', kind: 'int' }, { name: 'runs', kind: 'int' }, { name: 'last_run', label: 'last run', kind: 'run' }]} />
                </Panel>
              </div>
              <div className="columns two">
                <Panel title={`Latest ${found.recent.length}`}>
                  <Grid rows={found.recent} page={20} columns={[{ name: 'run', kind: 'run' }, { name: 'n', kind: 'int' }, { name: 'date' }, { name: 'command', kind: 'name' }, { name: 'params', label: 'parameters', kind: 'params' }, { name: 'status', kind: 'status' }, { name: 'unverified', kind: 'bool' }, { name: 'detail', label: 'response', kind: 'text' }]} />
                </Panel>
                <Panel title="Runs">
                  <Grid rows={shared(found.runs)} page={20} search={false} sort={{ name: 'run', desc: true }} columns={[{ name: 'run', kind: 'run' }, ...plain]} />
                </Panel>
              </div>
            </>
          )
        }}
      </Waiting>
    </div>
  )
}
