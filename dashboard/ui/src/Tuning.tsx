import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { request, useApi } from './api'
import { Dots } from './charts'
import { colors, label, num, span, time } from './format'
import { Facts, Figures, Grid, Panel, Pill, Waiting, columnsOf } from './Grid'

function tone(state: string | null) {
  return state === 'running' ? 'live' : state === 'failed' || state === 'interrupted' ? 'bad' : 'plain'
}

export function Tuning() {
  const tuning = useApi('/api/tuning', 10000)
  return (
    <div className="page">
      <h1>Tuning</h1>
      <Waiting loaded={tuning}>
        {() => (
          <>
            <Panel title="Installed">
              <Grid fold search={false} rows={tuning.data.installed} columns={columnsOf(tuning.data.installed, [{ name: 'model', kind: 'name' }, { name: 'trial', kind: 'int' }, { name: 'installed_at', label: 'installed', kind: 'time' }]).map((column) => (column.name === 'search' ? { ...column, kind: 'text' } : column))} />
            </Panel>
            <Panel title="Searches">
              <Grid
                rows={tuning.data.rows}
                facets={['model', 'state']}
                columns={[
                  { name: 'search', render: (row) => <Link to={`/tuning/${row.search}/${row.model}`}>{row.search}</Link> },
                  { name: 'model' },
                  { name: 'state', render: (row) => (row.state ?? row.job ? <Pill value={row.state ?? row.job} tone={tone(row.state ?? row.job)} /> : null) },
                  { name: 'finished', label: 'trials', kind: 'int' },
                  { name: 'requested', kind: 'int' },
                  { name: 'winner', label: 'winner', kind: 'int' },
                  { name: 'winner_loss', label: 'winner loss', kind: 'num' },
                  { name: 'installed', kind: 'bool' },
                  { name: 'differentiation_weight', kind: 'frac', group: 'loss weights' },
                  { name: 'reward_weight', kind: 'frac', group: 'loss weights' },
                  { name: 'points_per_run', kind: 'int' },
                  { name: 'threads', kind: 'int' },
                  { name: 'memory_gb', label: 'memory GiB', kind: 'num' },
                  { name: 'seconds', label: 'duration', render: (row) => (row.seconds ? span(row.seconds) : '') },
                ]}
              />
            </Panel>
            <Panel title="Loss settings">
              <Facts items={Object.entries(tuning.data.metric).map(([name, value]) => [name, String(value)])} />
            </Panel>
          </>
        )}
      </Waiting>
    </div>
  )
}

function Weights({ search, model, weights, reload }: { search: string; model: string; weights: any; reload: () => void }) {
  const shown = (value: number) => String(Number(value.toPrecision(6)))
  const [differentiation, setDifferentiation] = useState(shown(weights.weights.differentiation))
  const [reward, setReward] = useState(shown(weights.weights.reward))
  const [problem, setProblem] = useState<string | null>(null)
  useEffect(() => {
    setDifferentiation(shown(weights.weights.differentiation))
    setReward(shown(weights.weights.reward))
  }, [weights.revision])
  const apply = () =>
    request(`/api/tuning/${search}/${model}/weights`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision: weights.revision, differentiation: Number(differentiation), reward: Number(reward) }) }).then(
      () => {
        setProblem(null)
        reload()
      },
      (error) => setProblem(error.message),
    )
  return (
    <Panel title="Loss weights" extra={`revision ${weights.revision} · set ${time(weights.updated)}`}>
      <div className="form">
        <label>
          differentiation <input value={differentiation} onChange={(event) => setDifferentiation(event.target.value)} />
        </label>
        <label>
          reward <input value={reward} onChange={(event) => setReward(event.target.value)} />
        </label>
        <button onClick={apply} disabled={differentiation === shown(weights.weights.differentiation) && reward === shown(weights.weights.reward)}>
          apply
        </button>
        {problem && <span className="problem">{problem}</span>}
      </div>
    </Panel>
  )
}

export function Search() {
  const { search, model } = useParams() as { search: string; model: string }
  const [query, setQuery] = useSearchParams()
  const picked = query.get('trial')
  const detail = useApi(`/api/tuning/${search}/${model}`, 10000)
  const config = useApi(picked ? `/api/tuning/${search}/${model}/trials/${picked}` : null)
  const panel = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    panel.current?.scrollIntoView({ block: 'nearest' })
  }, [picked, config.data === undefined])
  return (
    <div className="page">
      <h1>
        {label(model)} search {search}
        <span className="extra">
          <Link to="/tuning">all searches</Link>
        </span>
      </h1>
      <Waiting loaded={detail}>
        {() => {
          const found = detail.data
          const rows: any[] = found.rows
          const done = rows.filter((row) => row.loss !== null)
          let best = Infinity
          const trend = done.map((row) => [row.trial, (best = Math.min(best, row.loss))] as [number, number])
          const winner = rows.find((row) => row.trial === found.winner)
          const current = found.status?.current
          return (
            <>
              <Figures
                items={[
                  ['state', found.state ? <Pill value={found.state} tone={tone(found.state)} /> : '—'],
                  ['trials', num(rows.length), `of ${num(found.request?.trials)}`],
                  ['completed', num(done.length)],
                  ...[...new Set(rows.filter((row) => row.state !== 'completed').map((row) => row.state))].map((state) => [label(String(state)), num(rows.filter((row) => row.state === state).length)] as [string, string]),
                  ['lowest loss', num(best === Infinity ? null : best), found.baseline ? `baseline ${num(found.baseline.loss)}` : undefined],
                  ['winner', found.winner ?? '—', winner ? `loss ${num(winner.loss)}` : undefined],
                  ['installed', found.installed ?? '—'],
                ]}
              />
              {current && <Facts items={[['running trial', current.trial], ['seconds', num(current.seconds, 3)], ['memory GiB', num(current.memory_gb, 3)], ['step', current.detail?.step ?? '']]} />}
              {found.status?.error && <pre className="problem">{found.status.error}</pre>}
              <Weights search={search} model={model} weights={found.weights} reload={detail.reload} />
              <Panel title="Loss by trial">
                <Dots points={done.map((row) => ({ x: row.trial, y: row.loss, key: row.method ?? 'trial', title: `trial ${row.trial}`, to: `/tuning/${search}/${model}?trial=${row.trial}` }))} palette={colors([...new Set(done.map((row) => row.method ?? 'trial'))] as string[])} line={trend} zero={false} height={220} />
              </Panel>
              {picked && (
                <div ref={panel}>
                <Panel title={`Trial ${picked}`} extra={<a onClick={() => setQuery({})}>close</a>}>
                  <Waiting loaded={config}>
                    {() => (
                      <>
                        {config.data.proposal && <Facts items={Object.entries(config.data.proposal).filter(([, value]) => typeof value !== 'object').map(([name, value]) => [name, typeof value === 'number' ? num(value) : String(value)])} />}
                        <Grid rows={Object.entries(config.data.config).map(([setting, value]) => ({ setting, value }))} page={40} columns={[{ name: 'setting', kind: 'text' }, { name: 'value', kind: 'text' }]} />
                      </>
                    )}
                  </Waiting>
                </Panel>
                </div>
              )}
              <Panel title="Trial results">
                <Grid
                  fold
                  rows={rows}
                  sort={{ name: 'loss', desc: false }}
                  facets={['state', 'method']}
                  columns={[
                    { name: 'trial', render: (row) => <a onClick={() => setQuery({ trial: String(row.trial) })}>{row.trial}</a> },
                    { name: 'state', render: (row) => <Pill value={row.state} tone={row.state === 'completed' ? 'plain' : 'warn'} /> },
                    { name: 'loss', kind: 'num' },
                    ...columnsOf(rows).filter((column) => found.measures.includes(column.name)),
                    ...columnsOf(rows).filter((column) => !['trial', 'state', 'loss', ...found.measures, ...found.settings].includes(column.name)),
                  ]}
                />
              </Panel>
              <Panel title="Trial settings">
                <Grid fold rows={rows} sort={{ name: 'loss', desc: false }} columns={[{ name: 'trial', render: (row) => <a onClick={() => setQuery({ trial: String(row.trial) })}>{row.trial}</a> }, { name: 'loss', kind: 'num' }, ...columnsOf(rows).filter((column) => found.settings.includes(column.name))]} />
              </Panel>
            </>
          )
        }}
      </Waiting>
    </div>
  )
}
