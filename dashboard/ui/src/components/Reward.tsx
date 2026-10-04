import { Link } from 'react-router-dom'
import { Card, Loading } from '@/components/primitives'
import { useApi, type S } from '@/lib/api'
import { num } from '@/lib/format'

const NAMES: Record<string, string> = { stock: 'Building stock', population: 'Population', gdp: 'GDP' }
const PARTS: [keyof S['RewardPart'], string][] = [
  ['end_ratio', 'Ending / start'], ['recent_change', 'Recent change / yr'], ['part', 'Reward part'],
  ['weight', 'Weight'], ['alpha', 'T exponent'], ['duration_factor', 'Time factor'], ['contribution', 'Contribution'],
]

export function RewardFormula() {
  return <div className="space-y-2 text-sm">
    <p className="font-mono text-xs sm:text-sm">R = [√T(k + Δk)/2 + 6TΔp + (g + Δg)/√T] / 9</p>
    <p className="text-dim">Building stock (k), population (p) and GDP (g) are divided by their starting values. Δ is their annualized change over the final year, or the full remaining interval when shorter. T is the interval in game years.</p>
    <p className="text-dim">Initializers start at the run’s opening snapshot. Both CatBoost pickers start at the pause’s first snapshot. Defeat sets all three ending values to zero; debt cutoff keeps the recorded values.</p>
  </div>
}

export function Reward({ run, seq }: { run: number; seq?: number }) {
  const found = useApi<S['RunReward']>(`/api/policy/runs/${run}/reward${seq === undefined ? '' : `?seq=${seq}`}`, { live: true })
  return <Loading state={found}>{reward => !reward.parts.length
    ? <Card className="text-dim w-fit px-3 py-2 text-sm">{reward.unavailable_reason}</Card>
    : <div className="space-y-3">
      <p className="text-dim text-xs">Baseline: <Link className="linka" to={`/runs/${run}/snapshots/${reward.baseline_seq}`}>snapshot {reward.baseline_seq}</Link> · {num(reward.years!)} game years · recent window {num(reward.window_years!)} years{reward.defeated ? ' · defeated, ending values set to zero' : ''}</p>
      <Card className="max-w-full overflow-x-auto">
        <table className="w-full whitespace-nowrap text-xs">
          <thead><tr className="border-line text-dim border-b"><th className="px-3 py-2 text-left font-medium">Metric</th>{PARTS.map(([key, label]) => <th key={key} className="px-3 py-2 text-right font-medium">{label}</th>)}</tr></thead>
          <tbody>{reward.parts.map(part => <tr key={part.component} className="border-line/60 border-b"><td className="px-3 py-2">{NAMES[part.component]}</td>{PARTS.map(([key]) => <td key={key} className="num px-3 py-2 text-right">{num(part[key] as number)}</td>)}</tr>)}
            <tr><td className="px-3 py-2 font-semibold" colSpan={PARTS.length}>Current reward</td><td className="num px-3 py-2 text-right font-semibold">{num(reward.score!)}</td></tr>
          </tbody>
        </table>
      </Card>
      <p className="text-dim text-xs">Buildings and GDP use (ending ratio + recent change) / 2. Population uses recent change. Each contribution is reward part × weight × time factor.</p>
    </div>
  }</Loading>
}
