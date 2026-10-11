import { Link, useOutletContext } from 'react-router-dom'
import { useApi } from './api'
import { Columns, Dots } from './charts'
import { clock, colors, groupBy, label, median, num, phaseTone, span } from './format'
import { Facts, Figures, Grid, Panel, Pill, Waiting } from './Grid'
import { stateColumn } from './Runs'

const HOUR = 3600000

function Collection({ found, rows }: { found: any; rows: any[] }) {
  if (!found) return null
  const settings = found.settings
  if (!settings) return <Panel title="Collection">none</Panel>
  const now = Date.now()
  const recent = rows.filter((row) => row.ended && now - Date.parse(row.ended) < 3 * HOUR).length / 3
  const left = settings.runs - found.completed
  return (
    <Panel
      title={
        <>
          Collection <Pill value={found.phase} tone={phaseTone(found.phase)} />
        </>
      }
      extra={
        found.run_id && (
          <>
            <Link to={`/runs/${found.run_id}`}>run {found.run_id}</Link> · {found.date} · {label(found.step ?? '')} · snapshot {found.snapshot}
          </>
        )
      }
    >
      {found.error && <div className="problem">{found.error}</div>}
      <div className="progress">
        <div className="progress-track">
          <div style={{ width: `${(100 * found.completed) / settings.runs}%` }} />
        </div>
        <span>
          <b>{num(found.completed)}</b> of {num(settings.runs)} runs
          {recent > 0 && (
            <>
              {' '}
              · {num(recent, 2)} per hour · {span((left / recent) * 3600)} left
            </>
          )}
        </span>
      </div>
      <Facts items={Object.entries(settings).map(([name, value]) => [name, Array.isArray(value) ? value.join(', ') : name === 'world_cache' ? String(value).split(/[\\/]/).pop() : String(value)])} />
    </Panel>
  )
}

export function Overview() {
  const found = useOutletContext<any>()
  const runs = useApi('/api/runs', 15000)
  return (
    <div className="page">
      <Waiting loaded={runs}>
        {() => {
          const rows: any[] = runs.data.rows
          const ended = rows.filter((row) => row.ended)
          const states = [...new Set(ended.map((row) => row.state))].sort()
          const palette = colors(states)
          const now = Date.now()
          const start = Math.floor(now / HOUR) * HOUR - 23 * HOUR
          const hours = Array.from({ length: 24 }, (_, index) => {
            const from = start + index * HOUR
            const inside = ended.filter((row) => Date.parse(row.ended) >= from && Date.parse(row.ended) < from + HOUR)
            return { label: `${String(new Date(from).getHours()).padStart(2, '0')}h`, title: `${clock(new Date(from).toISOString())} to ${clock(new Date(from + HOUR).toISOString()).slice(6)}`, values: Object.fromEntries(states.map((state) => [state, inside.filter((row) => row.state === state).length])) }
          })
          const endings = [...groupBy(ended, (row) => row.state).entries()].map(([state, group]) => ({ state, tone: group[0].tone, runs: group.length, share: group.length / ended.length, game_years: median(group.map((row) => row.game_years)) }))
          return (
            <>
              <Collection found={found} rows={rows} />
              <Figures
                items={[
                  ['runs', num(rows.length)],
                  ['ended', num(ended.length)],
                  ['last hour', num(ended.filter((row) => now - Date.parse(row.ended) < HOUR).length)],
                  ['median game years', num(median(ended.map((row) => row.game_years))), `of ${found?.settings?.years ?? ''}`],
                  ['median minutes', num(median(ended.map((row) => row.minutes))), `of ${found?.settings?.minutes ?? ''}`],
                ]}
              />
              <div className="columns three">
                <Panel title="Runs per hour" extra="24 h">
                  <Columns data={hours} keys={states} palette={palette} />
                </Panel>
                <Panel title="Game years">
                  <Dots points={ended.map((row) => ({ x: row.run, y: row.game_years, key: row.state, title: `run ${row.run} · ${row.country}`, to: `/runs/${row.run}` }))} palette={palette} xTitle="run" yTitle="game years" />
                </Panel>
                <Panel title="End reasons">
                  <Grid search={false} sort={{ name: 'runs', desc: true }} rows={endings} columns={[stateColumn, { name: 'runs', kind: 'int' }, { name: 'share', kind: 'share' }, { name: 'game_years', label: 'median years', kind: 'num' }]} />
                </Panel>
              </div>
              <Panel title="Latest runs" extra={<Link to="/runs">all {rows.length}</Link>}>
                <Grid search={false} sort={{ name: 'run', desc: true }} page={12} rows={[...rows].sort((a, b) => b.run - a.run).slice(0, 12)} columns={[{ name: 'run', kind: 'run' }, stateColumn, { name: 'started', kind: 'time' }, { name: 'minutes', kind: 'num' }, { name: 'country', kind: 'name' }, { name: 'game_years', label: 'game years', kind: 'num' }, { name: 'attempted', kind: 'int' }, ...runs.data.statuses.map((status: string) => ({ name: status, kind: 'int' })), { name: 'unverified', kind: 'int' }]} />
              </Panel>
            </>
          )
        }}
      </Waiting>
    </div>
  )
}
