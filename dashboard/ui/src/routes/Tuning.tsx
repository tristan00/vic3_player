import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { LineChart } from '@/components/charts'
import { Card, ErrorState, Section } from '@/components/primitives'
import { useApi, type S } from '@/lib/api'
import { GraphTuning } from './GraphTuning'

type Trial = S['Trial']
type Results = S['Results']
const number = (value: number | null | undefined, digits = 4) => value == null ? '—' : value.toFixed(digits)

function Tradeoff({ trials, best, selected, onSelect }: { trials: Trial[]; best: number | null; selected: number | null; onSelect: (trial: number) => void }) {
  const valid = trials.filter((trial) => trial.score != null)
  const xmax = Math.max(1, ...valid.map((trial) => trial.reward_loss!)) * 1.05
  const x = (value: number) => 60 + value / xmax * 590
  const y = (value: number) => 210 - value * 180
  return <svg viewBox="0 0 680 255" className="w-full" role="img" aria-label="Reward loss versus entropy loss; lower left is better">
    {[0, .25, .5, .75, 1].map((tick) => <g key={tick}>
      <line x1="60" x2="650" y1={y(tick)} y2={y(tick)} stroke="var(--grid)" />
      <text x="49" y={y(tick) + 4} textAnchor="end" fontSize="11" fill="var(--dim)">{tick.toFixed(2)}</text>
    </g>)}
    {[0, .25, .5, .75, 1].map((part) => <text key={part} x={x(part * xmax)} y="227" textAnchor="middle" fontSize="11" fill="var(--dim)">{(part * xmax).toFixed(2)}</text>)}
    <text x="350" y="249" textAnchor="middle" fontSize="12" fill="var(--dim)">Normalized reward loss →</text>
    <text transform="translate(15 130) rotate(-90)" textAnchor="middle" fontSize="12" fill="var(--dim)">Entropy loss →</text>
    {valid.map((trial) => <circle key={trial.trial} cx={x(trial.reward_loss!)} cy={y(trial.entropy_loss!)} r={trial.trial === best ? 6 : 4}
      fill={trial.trial === best ? 'var(--done)' : 'var(--series)'} opacity={trial.trial === selected || trial.trial === best ? 1 : .5}
      stroke={trial.trial === selected ? 'var(--fg)' : 'none'} strokeWidth="2" tabIndex={0} role="button"
      aria-label={`Trial ${trial.trial}, loss ${number(trial.score)}`} onClick={() => onSelect(trial.trial)}
      onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(trial.trial) } }} className="cursor-pointer">
      <title>{`Trial ${trial.trial} · blend ${number(trial.score)} · reward ${number(trial.reward_loss)} · entropy ${number(trial.entropy)}`}</title>
    </circle>)}
  </svg>
}

function View({ data }: { data: Results }) {
  const [selected, setSelected] = useState<number | null>(null)
  const [sort, setSort] = useState<'score' | 'recent'>('score')
  const [includeTimeouts, setIncludeTimeouts] = useState(true)
  const best = data.trials.find((trial) => trial.trial === data.best)
  const chosen = data.trials.find((trial) => trial.trial === selected) ?? best
  const rewardContribution = (chosen?.reward_loss ?? 0) * data.reward_weight
  const entropyContribution = (chosen?.entropy_loss ?? 0) * data.entropy_weight
  const contributionWidth = (value: number) => chosen?.score ? `${value / chosen.score * 100}%` : '0%'
  let lowest = Infinity
  const history = data.trials.filter((trial) => trial.score != null).map((trial) => {
    lowest = Math.min(lowest, trial.score!)
    return { trial: trial.trial, score: lowest }
  })
  const rows = data.trials.filter((trial) => includeTimeouts || trial.state === 'completed').sort((a, b) =>
    sort === 'recent' ? b.trial - a.trial : (a.score ?? Infinity) - (b.score ?? Infinity) || a.trial - b.trial)
  const steps = data.model === 'histogram' ? ['prepare', 'tune', 'install', 'collect'] : ['tune']
  const running = data.state === 'running'
  return <div className="space-y-5">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-xl font-semibold">{data.title} tuning</h1><p className="text-dim mt-1 text-sm">{data.reward_weight * 100}% normalized reward loss + {data.entropy_weight * 100}% entropy loss. Lower blended loss is better.</p></div>
      <div className="text-right text-xs"><div className={data.state === 'failed' ? 'text-invalid' : running ? 'text-accent' : 'text-dim'}>{data.phase} · {data.state}</div><div className="text-dim mt-1">Updated {new Date(data.updated_at).toLocaleTimeString()} · refreshes every 5s</div></div>
    </div>
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm"><div className="flex gap-4">{steps.map((step, index) => <span key={step} className={step === data.phase ? 'text-accent font-semibold' : 'text-dim'}>{index + 1}. {step === 'tune' ? 'Tune' : step === 'collect' ? 'Collect' : step === 'install' ? 'Verify & install' : 'Prepare candidates'}</span>)}</div><span className="num">{data.finished.toLocaleString()} / {data.requested.toLocaleString()} trials</span></div>
      <progress max={data.requested} value={data.finished} className="h-2 w-full accent-[var(--accent)]" aria-label="Tuning progress" />
      <div className="text-dim mt-2 flex flex-wrap justify-between gap-2 text-xs"><span>{data.completed} completed · {data.timeouts} timed out · {data.seconds_limit}s hard limit</span><span>{data.installed == null ? 'Winner installation pending' : `Installed trial ${data.installed}`}</span></div>
    </Card>
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {[
        ['Best blended loss', number(best?.score), best ? `Trial ${best.trial} · lower is better` : 'Awaiting a completed trial'],
        ['Reward RMSE', number(best?.rmse), `Normalized loss ${number(best?.reward_loss)}`],
        [data.model === 'histogram' ? 'Candidate entropy' : 'Action entropy', best?.entropy == null ? '—' : `${(100 * best.entropy).toFixed(2)}%`, 'Higher means more distinct predictions'],
        ['Constant baseline', number(data.baseline), best ? `${((1 - best.score! / data.baseline) * 100).toFixed(1)}% lower loss than constant predictions` : 'Same validation objective'],
      ].map(([label, value, detail]) => <Card key={label} className="p-4"><p className="text-dim text-xs">{label}</p><div className="num mt-1 text-2xl font-semibold">{value}</div><p className="text-dim mt-1 text-xs">{detail}</p></Card>)}
    </div>
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-4"><Section title="Best loss so far" right={<span className="text-dim text-xs">Lower is better</span>}>
        <LineChart xs={history.map((point) => point.trial)} ys={history.map((point) => point.score)} height={270} step xFormat={(value) => `#${value}`} yFormat={(value) => number(value, 3)}
          onPick={(index) => setSelected(history[index].trial)} tip={(index) => `Trial ${history[index].trial} · best loss ${number(history[index].score)}`} empty="Waiting for the first completed trial" />
      </Section></Card>
      <Card className="p-4"><Section title="Reward loss & differentiation" right={<span className="text-dim text-xs">Lower left is better · green = best</span>}>
        <Tradeoff trials={data.trials} best={data.best} selected={chosen?.trial ?? null} onSelect={setSelected} />
      </Section></Card>
    </div>
    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
      <Card className="min-w-0 p-4"><Section title="Trials" right={<div className="flex items-center gap-3 text-xs"><label className="flex gap-1.5"><input type="checkbox" checked={includeTimeouts} onChange={(event) => setIncludeTimeouts(event.target.checked)} />Show timeouts</label><select aria-label="Sort trials" value={sort} onChange={(event) => setSort(event.target.value as 'score' | 'recent')} className="border-line bg-surface rounded border px-2 py-1"><option value="score">Best loss first</option><option value="recent">Newest first</option></select></div>}>
        <div className="max-h-[430px] overflow-auto"><table className="world-table w-full text-left text-xs"><thead className="bg-surface sticky top-0"><tr>{['Trial', 'Blended loss', 'Reward loss', 'Entropy', 'Time', 'State'].map((label) => <th className="px-3 py-2 font-medium" key={label}>{label}</th>)}</tr></thead><tbody>
          {rows.map((trial) => <tr key={trial.trial} className={chosen?.trial === trial.trial ? 'bg-accent-soft' : ''}><td><button className="linka whitespace-nowrap font-medium" onClick={() => setSelected(trial.trial)}>#{trial.trial}{trial.trial === data.best ? ' ★' : ''}</button></td><td className="num">{number(trial.score)}</td><td className="num">{number(trial.reward_loss)}</td><td className="num">{trial.entropy == null ? '—' : `${(100 * trial.entropy).toFixed(1)}%`}</td><td className="num">{number(trial.seconds, 1)}s</td><td className={trial.state === 'time_limit' ? 'text-invalid' : 'text-dim'}>{trial.state === 'time_limit' ? 'Timed out' : trial.state}</td></tr>)}
        </tbody></table></div><p className="text-dim mt-2 text-xs">Timed-out trials have no validation score and cannot win.</p>
      </Section></Card>
      <Card className="p-4"><Section title={chosen ? `Trial ${chosen.trial} parameters` : 'Trial parameters'} right={<button className="linka text-xs" onClick={() => setSelected(null)}>Show best</button>}>
        {chosen && <><div className="text-dim mb-3 text-xs">{chosen.trial === data.best ? 'Best completed trial' : 'Selected trial'}{chosen.histograms != null ? ` · ${chosen.histograms} histograms · ${chosen.bins} bins` : ''}</div>
          <dl className="space-y-1.5 text-xs">{Object.entries(chosen.params).map(([name, value]) => <div className="flex justify-between gap-3" key={name}><dt className="text-dim break-all">{name}</dt><dd className="num text-right">{typeof value === 'number' && !Number.isInteger(value) ? value.toPrecision(6) : String(value)}</dd></div>)}</dl>
          {chosen.score != null && <div className="border-line mt-4 border-t pt-3 text-xs"><p className="mb-2 font-medium">{data.reward_weight * 100}/{data.entropy_weight * 100} score contributions</p><div className="num flex justify-between"><span>Reward {number(rewardContribution)}</span><span>Entropy {number(entropyContribution)}</span></div><div className="bg-raised mt-2 flex h-2 overflow-hidden rounded"><div className="bg-[var(--series)]" style={{ width: contributionWidth(rewardContribution) }} /><div className="bg-[var(--done)]" style={{ width: contributionWidth(entropyContribution) }} /></div></div>}
        </>}
        {chosen?.trial === data.best && data.best_sizes && <details className="border-line mt-4 border-t pt-3 text-xs"><summary className="cursor-pointer">Winning histogram sizes</summary><dl className="mt-3 space-y-1">{Object.entries(data.best_sizes).sort(([a], [b]) => a.localeCompare(b)).map(([name, size]) => <div className="flex justify-between gap-2" key={name}><dt className="text-dim break-all">{name}</dt><dd className="num">{size}</dd></div>)}</dl></details>}
      </Section></Card>
    </div>
    {Object.keys(data.ranges).length > 0 && <Card className="p-4"><details><summary className="cursor-pointer text-sm font-medium">Full search space · {Object.values(data.ranges).filter(Array.isArray).length} tunable CatBoost parameters</summary>
      <p className="text-dim my-3 text-xs">Each trial shows only its active parameters. Subsample applies to MVS/Bernoulli; bagging temperature to Bayesian; minimum leaf size to Depthwise/Lossguide; maximum leaves to Lossguide. Ordered boosting requires SymmetricTree.</p>
      <dl className="grid gap-x-8 gap-y-2 text-xs sm:grid-cols-2">{Object.entries(data.ranges).map(([name, values]) => <div className="flex justify-between gap-3" key={name}><dt className="text-dim">{name}</dt><dd className="num text-right">{Array.isArray(values) ? values.length === 2 && typeof values[0] === 'number' && ['iterations', 'depth', 'learning_rate', 'l2_leaf_reg', 'rsm', 'random_strength', 'subsample', 'bagging_temperature'].includes(name) ? `${values[0]}–${values[1]}` : values.join(', ') : `${values} (fixed)`}</dd></div>)}</dl>
      {data.model === 'histogram' && <p className="text-dim mt-3 text-xs">Histogram inclusion and bin counts are also tuned. Tree count is capped by 409600 / 2^depth.</p>}
    </details></Card>}
    <p className="text-dim text-xs">{data.model === 'histogram' ? 'Entropy is measured across 30 fixed random candidate blocks at each sampled validation pause.' : 'Entropy is measured across the selected action predictions within each validation pause.'} Predictions within the numerical tolerance are grouped as ties. Equal predictions score 0; all distinct predictions score 1. Trial numbers start at 0.</p>
  </div>
}

function TrialResults({ model }: { model: 'histogram' | 'row' }) {
  const state = useApi<Results>(`/api/tuning/${model}`)
  useEffect(() => { const timer = setInterval(state.reload, 5000); return () => clearInterval(timer) }, [state.reload])
  return <>
    {state.error && <ErrorState error={state.error} onRetry={state.reload} />}
    {state.data && !state.stale ? <View key={model} data={state.data} /> : !state.error && <Card className="p-8 text-center text-dim">Loading tuning results…</Card>}
  </>
}

export function Tuning() {
  const [params, setParams] = useSearchParams()
  const model = params.get('model') === 'world' ? 'world' : params.get('model') === 'row' ? 'row' : 'histogram'
  return <div className="mx-auto max-w-[1600px] space-y-4">
    <div className="flex flex-wrap gap-2" aria-label="Tuning models">{[['histogram', 'Whole-block'], ['row', 'Piecewise'], ['world', 'Full world graph']].map(([key, label]) => <button key={key} aria-pressed={model === key} className={`rounded px-3 py-1.5 text-sm ${model === key ? 'bg-accent-soft text-accent font-semibold' : 'text-dim hover:bg-raised'}`} onClick={() => setParams({ model: key })}>{label}</button>)}</div>
    {model === 'world' ? <GraphTuning /> : <TrialResults key={model} model={model} />}
  </div>
}
