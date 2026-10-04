import { useEffect, useState } from 'react'
import { LineChart } from '@/components/charts'
import { Card, ErrorState, Section } from '@/components/primitives'
import { useApi, type S } from '@/lib/api'

type Tracking = S['GraphTracking']
type Run = S['GraphRun']
const number = (value: number | null | undefined, digits = 4) => value == null ? '—' : value.toFixed(digits)
const words = (value: string) => value.replaceAll('_', ' ')
const parameterName = (name: string) => name === 'layers' ? 'Message-passing rounds' : words(name)

function RunView({ run }: { run: Run }) {
  const [selected, setSelected] = useState<string | null>(null)
  const chosen = run.trials.find((trial) => trial.name === selected)
    ?? run.trials.find((trial) => trial.state === 'running')
    ?? run.trials.find((trial) => trial.name === run.selected)
    ?? run.trials[0]
  const best = run.trials.find((trial) => trial.name === run.selected)
  const running = run.trials.filter((trial) => trial.state === 'running')
  return <div className="space-y-4">
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap justify-between gap-2 text-sm"><span className={run.state === 'failed' || run.state === 'interrupted' ? 'text-invalid' : run.state === 'running' ? 'text-accent' : 'text-dim'}>{words(run.phase)} · {words(run.state)}</span><span className="num">{run.completed} / {run.requested} fits completed</span></div>
      <progress aria-label="Graph fits completed" max={Math.max(1, run.requested)} value={run.completed} className="h-2 w-full accent-[var(--accent)]" />
      <p className="text-dim mt-2 text-xs">{running.length} active · {run.failed} failed or interrupted · last activity {new Date(run.updated_at).toLocaleString()}</p>
      {run.error && <p className="text-invalid mt-2 text-sm">{run.error}</p>}
    </Card>
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {[
        ['Best validation score', number(best?.validation?.score), best ? words(best.name) : 'Awaiting a completed fit'],
        ['Validation sequence error', number(best?.validation?.sequence_nrmse), 'Normalized RMSE · lower is better'],
        ['Candidate entropy', best?.validation?.mean_pause_entropy == null ? '—' : `${number(best.validation.mean_pause_entropy * 100, 2)}%`, 'Validation candidates'],
        ['Active fit', running.length ? words(running[0].name) : 'None', running.length ? `Epoch ${running[0].epoch} / ${running[0].epoch_limit} · ${words(running[0].phase)}` : words(run.state)],
      ].map(([label, value, detail]) => <Card key={label} className="p-4"><p className="text-dim text-xs">{label}</p><div className="num mt-1 break-words text-xl font-semibold">{value}</div><p className="text-dim mt-1 text-xs">{detail}</p></Card>)}
    </div>
    <Card className="p-4"><Section title="Fits" right={<span className="text-dim text-xs">Select a fit for its epochs and parameters</span>}>
      <div className="overflow-auto"><table className="world-table w-full text-left text-xs"><thead><tr>{['Fit', 'State / phase', 'Message rounds', 'Epoch', 'Validation sequence', 'Test sequence', 'Validation score', 'Test score', 'Fit time', 'Peak GPU'].map((label) => <th key={label} className="whitespace-nowrap px-3 py-2 font-medium">{label}</th>)}</tr></thead><tbody>
        {run.trials.map((trial) => <tr key={trial.name} className={chosen?.name === trial.name ? 'bg-accent-soft' : ''}>
          <td><button className="linka whitespace-nowrap" onClick={() => setSelected(trial.name)}>{words(trial.name)}{trial.name === run.selected ? ' ★' : ''}</button></td>
          <td className={['failed', 'interrupted'].includes(trial.state) ? 'text-invalid' : 'text-dim'}>{words(trial.state)}{trial.state === 'running' ? ` · ${words(trial.phase)}` : ''}</td>
          <td className="num">{trial.params.layers ?? '—'}</td>
          <td className="num whitespace-nowrap">{trial.epoch} / {trial.epoch_limit}</td><td className="num">{number(trial.validation?.sequence_nrmse ?? trial.epochs.at(-1)?.validation_sequence_nrmse)}</td><td className="num">{number(trial.test?.sequence_nrmse)}</td><td className="num">{number(trial.validation?.score)}</td><td className="num">{number(trial.test?.score)}</td><td className="num whitespace-nowrap">{trial.seconds == null ? '—' : `${number(trial.seconds / 60, 1)} min`}</td><td className="num whitespace-nowrap">{trial.gpu_peak_bytes == null ? '—' : `${number(trial.gpu_peak_bytes / 1e9, 2)} GB`}</td>
        </tr>)}
      </tbody></table></div>
    </Section></Card>
    {chosen && <>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
        <div className="min-w-0 space-y-4">
          <Card className="p-4"><Section title={`${words(chosen.name)} · validation by epoch`} right={<span className="text-dim text-xs">Selected epoch {chosen.best_epoch ?? '—'}</span>}>
            <LineChart xs={chosen.epochs.map((epoch) => epoch.epoch)} ys={chosen.epochs.map((epoch) => epoch.validation_sequence_nrmse)} height={240} xFormat={(value) => `Epoch ${value}`} yFormat={(value) => number(value, 3)} tip={(index) => `Epoch ${chosen.epochs[index].epoch} · sequence RMSE ${number(chosen.epochs[index].validation_sequence_nrmse)}`} empty="Waiting for the first completed epoch" />
          </Section></Card>
          <Card className="p-4"><Section title="Training loss by epoch">
            <LineChart xs={chosen.epochs.map((epoch) => epoch.epoch)} ys={chosen.epochs.map((epoch) => epoch.training_mse)} height={190} xFormat={(value) => `Epoch ${value}`} yFormat={(value) => number(value, 3)} tip={(index) => `Epoch ${chosen.epochs[index].epoch} · training MSE ${number(chosen.epochs[index].training_mse)}`} empty="Waiting for the first completed epoch" />
          </Section></Card>
        </div>
        <Card className="p-4"><Section title="Fit parameters">
          {chosen.state === 'running' && <div className="mb-4 text-sm"><p>{words(chosen.phase)} · epoch {chosen.epoch} / {chosen.epoch_limit}</p>{chosen.total > 0 && <><progress aria-label="Current phase progress" max={chosen.total} value={chosen.done} className="mt-2 h-2 w-full accent-[var(--accent)]" /><p className="text-dim text-xs">{chosen.done} / {chosen.total} cases</p></>}</div>}
          {chosen.error && <p className="text-invalid mb-3 text-sm">{chosen.error}</p>}
          <dl className="space-y-2 text-xs">{Object.entries(chosen.params).map(([name, value]) => <div className="flex justify-between gap-3" key={name}><dt className="text-dim">{parameterName(name)}</dt><dd className="num text-right">{String(value)}</dd></div>)}</dl>
          <p className="text-dim mt-3 text-xs">Each message-passing round passes information across one graph edge.</p>
          {chosen.validation && <dl className="border-line mt-4 space-y-2 border-t pt-3 text-xs"><div className="flex justify-between gap-3"><dt className="text-dim">Validation reward loss</dt><dd className="num">{number(chosen.validation.reward_loss)}</dd></div><div className="flex justify-between gap-3"><dt className="text-dim">Candidate spread</dt><dd className="num">{number(chosen.validation.normalized_candidate_std)}</dd></div></dl>}
        </Section></Card>
      </div>
      <p className="text-dim text-xs">Best fit uses validation score. Epoch selection uses validation sequence error. Test scores are reported separately.</p>
    </>}
  </div>
}

function TrackingView({ data }: { data: Tracking }) {
  const [selectedRun, setSelectedRun] = useState('current')
  const run = selectedRun === 'current' ? data.runs.find((item) => item.graph_version === data.current_graph_version) : data.runs.find((item) => item.id === selectedRun)
  return <div className="space-y-4">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-xl font-semibold">Full world graph tuning</h1><p className="text-dim mt-1 text-sm">{run ? `Graph version ${run.graph_version} · ${run.label}` : `Graph version ${data.current_graph_version} · not started`}</p></div><div className="space-y-2 text-right"><select aria-label="Graph tuning run" value={selectedRun} onChange={(event) => setSelectedRun(event.target.value)} className="border-line bg-surface max-w-full rounded border px-2 py-1 text-sm"><option value="current">Current graph · v{data.current_graph_version}</option>{data.runs.map((item) => <option key={item.id} value={item.id}>{item.graph_version === data.current_graph_version ? 'Run' : `Earlier graph v${item.graph_version}`} · {item.label}</option>)}</select><p className="text-dim text-xs">Updated {new Date(data.updated_at).toLocaleTimeString()} · refreshes every 5s</p></div></div>
    {run && run.graph_version !== data.current_graph_version && <p className="border-line rounded border p-3 text-sm text-dim">Historical results from an earlier graph. These scores do not evaluate the current world structure.</p>}
    {run ? <RunView key={run.id} run={run} /> : <>
      <div className="grid gap-3 sm:grid-cols-3">{[['Planned fits', 'Not scheduled'], ['Completed fits', '0'], ['Active fits', '0']].map(([label, value]) => <Card className="p-4" key={label}><p className="text-dim text-xs">{label}</p><p className="num mt-1 text-xl font-semibold">{value}</p></Card>)}</div>
      <Card className="p-8 text-center"><h2 className="font-semibold">No tuning run has started for this graph</h2><p className="text-dim mt-2 text-sm">Fit progress, epoch curves, parameters and validation scores will appear here when the runner starts.</p></Card>
    </>}
    <p className="text-xs"><a className="linka" href="/tuning/world/report.html" target="_blank" rel="noreferrer">Open graph review separately</a></p>
  </div>
}

export function GraphTuning() {
  const state = useApi<Tracking>('/api/tuning/world')
  useEffect(() => { const timer = setInterval(state.reload, 5000); return () => clearInterval(timer) }, [state.reload])
  return <>{state.error && <ErrorState error={state.error} onRetry={state.reload} />}{state.data && !state.stale ? <TrackingView data={state.data} /> : !state.error && <Card className="text-dim p-8 text-center">Loading graph tuning progress…</Card>}</>
}
