import { useApi } from './api'
import { Columns, Dots } from './charts'
import { colors, groupBy, label, median, num } from './format'
import { Facts, Grid, Panel, Waiting } from './Grid'
import { stateColumn } from './Runs'

function summary(rows: any[], components: string[]) {
  const scored = rows.filter((row) => row.score !== null)
  return { runs: rows.length, scored: scored.length, score: median(scored.map((row) => row.score)), game_years: median(scored.map((row) => row.game_years)), ...Object.fromEntries(components.map((component) => [component, median(scored.map((row) => row[component]))])) }
}

function rolling(points: [number, number][], window: number): [number, number][] {
  return points.map((point, index) => [point[0], median(points.slice(Math.max(0, index - window + 1), index + 1).map((other) => other[1]))!])
}

function histogram(values: number[], bins: number, clip: [number, number]) {
  const ordered = [...values].sort((a, b) => a - b)
  const low = ordered[Math.floor(clip[0] * (ordered.length - 1))]
  const high = ordered[Math.ceil(clip[1] * (ordered.length - 1))]
  const width = (high - low) / bins || 1
  const counts = Array.from({ length: bins }, () => 0)
  for (const value of values) counts[Math.max(0, Math.min(bins - 1, Math.floor((value - low) / width)))] += 1
  return counts.map((count, index) => {
    const from = index === 0 ? ordered[0] : low + index * width
    const to = index === bins - 1 ? ordered[ordered.length - 1] : low + (index + 1) * width
    return { label: num(low + index * width, 2), title: `${num(from, 3)} to ${num(to, 3)}`, values: { runs: count } }
  })
}

export function Scores() {
  const runs = useApi('/api/runs', 30000)
  return (
    <div className="page">
      <h1>Scores</h1>
      <Waiting loaded={runs}>
        {() => {
          const found = runs.data
          const rows: any[] = found.rows
          const components: string[] = found.components
          const objective = found.objective
          const scored = rows.filter((row) => row.score !== null)
          const palette = colors([...new Set(rows.filter((row) => row.ended).map((row) => row.state))] as string[])
          const parts = components.map((component) => ({ component, ...Object.fromEntries(Object.entries(objective).filter(([, value]) => value && typeof value === 'object').map(([name, value]: [string, any]) => [name, value[component]])) }))
          const settings = Object.entries(objective).filter(([, value]) => !value || typeof value !== 'object')
          const partColumns = [...new Set(parts.flatMap((part) => Object.keys(part)))].filter((name) => name !== 'component')
          const measures = [{ name: 'runs', kind: 'int' }, { name: 'scored', kind: 'int' }, { name: 'score', label: 'median score', kind: 'num' }, { name: 'game_years', label: 'median years', kind: 'num' }, ...components.map((component) => ({ name: component, kind: 'num', group: 'median contribution' }))]
          const policies = [...groupBy(rows, (row) => `${row.initializer} / ${row.sizer} / ${row.picker}`).entries()].map(([policy, group]) => ({ policy, initializer: group[0].initializer, sizer: group[0].sizer, picker: group[0].picker, ...summary(group, components) }))
          const endings = [...groupBy(rows.filter((row) => row.ended), (row) => row.state).entries()].map(([state, group]) => ({ state, tone: group[0].tone, ...summary(group, components) }))
          const reasons = [...groupBy(rows.filter((row) => row.score === null && row.ended), (row) => row.not_scored ?? '').entries()].map(([reason, group]) => ({ reason, runs: group.length, latest: Math.max(...group.map((row) => row.run)) }))
          return (
            <>
              <Panel title="Reward">
                <Facts items={settings.map(([name, value]) => [name, String(value)])} />
                <Grid search={false} rows={parts} columns={[{ name: 'component' }, ...partColumns.map((name) => ({ name, kind: 'num' }))]} />
              </Panel>
              <Panel title="Score by run" extra="median of 15">
                <Dots points={scored.map((row) => ({ x: row.run, y: row.score, key: row.state, title: `run ${row.run} · ${row.country}`, to: `/runs/${row.run}` }))} palette={palette} line={rolling(scored.map((row) => [row.run, row.score]), 15)} xTitle="run" yTitle="score" clip={[0.03, 0.97]} />
              </Panel>
              <div className="columns two">
                <Panel title="Distribution" extra={`${scored.length} runs`}>
                  <Columns data={scored.length ? histogram(scored.map((row) => row.score), 24, [0.03, 0.97]) : []} keys={['runs']} palette={{ runs: '#2a78d6' }} height={190} legend={false} />
                </Panel>
                <Panel title="Score by game years">
                  <Dots points={scored.map((row) => ({ x: row.game_years, y: row.score, key: row.state, title: `run ${row.run} · ${row.country}`, to: `/runs/${row.run}` }))} palette={palette} xTitle="game years" yTitle="score" clip={[0.03, 0.97]} />
                </Panel>
              </div>
              <Panel title="Initializer, sizer and picker">
                <Grid search={false} rows={policies} sort={{ name: 'runs', desc: true }} columns={[{ name: 'initializer', kind: 'name' }, { name: 'sizer', kind: 'name' }, { name: 'picker', kind: 'name' }, ...measures]} />
              </Panel>
              <Panel title="End reason">
                <Grid search={false} rows={endings} sort={{ name: 'runs', desc: true }} columns={[stateColumn, ...measures]} />
              </Panel>
              {reasons.length > 0 && (
                <Panel title="Not scored">
                  <Grid search={false} rows={reasons} sort={{ name: 'runs', desc: true }} columns={[{ name: 'reason', render: (row) => (row.reason ? label(row.reason) : 'none') }, { name: 'runs', kind: 'int' }, { name: 'latest', label: 'latest run', kind: 'run' }]} />
                </Panel>
              )}
              <Panel title="Scored runs">
                <Grid fold rows={scored} sort={{ name: 'score', desc: true }} facets={['state', 'initializer', 'sizer', 'picker']} columns={[{ name: 'run', kind: 'run' }, stateColumn, { name: 'country', kind: 'name' }, { name: 'initializer', kind: 'name' }, { name: 'sizer', kind: 'name' }, { name: 'picker', kind: 'name' }, { name: 'game_years', label: 'game years', kind: 'num' }, { name: 'score', kind: 'num' }, ...components.map((component) => ({ name: component, kind: 'num', group: 'contribution' }))]} />
              </Panel>
            </>
          )
        }}
      </Waiting>
    </div>
  )
}
