import { Link } from 'react-router-dom'
import { Card } from '@/components/primitives'

export const PICKERS = {
  first: {
    title: 'First block',
    description: 'Executes the first sampled block. The collector generates one candidate, with no prediction or ranking.',
    score: 'No model score',
  },
  catboost: {
    title: 'Whole-block CatBoost',
    description: 'Predicts the three-metric reward for each complete block using action counts, holdings and game context. Selects the highest score.',
    score: 'One prediction per block; reward starts at the pause’s first snapshot',
  },
  catboost_piecewise: {
    title: 'Piecewise CatBoost',
    description: 'Predicts each action and parameter combination in the current game context, then averages those predictions across the block. Each repeated action counts in the average. Selects the highest mean.',
    score: 'Mean of action predictions; reward starts at the pause’s first snapshot',
  },
}

export function Pickers({ only, selected = 'all' }: { only?: string | null; selected?: string }) {
  return <div className={`grid gap-3 ${only ? '' : 'lg:grid-cols-3'}`}>
    {Object.entries(PICKERS).filter(([name]) => !only || name === only).map(([name, picker]) => (
      <Card key={name} className={`space-y-2 px-3 py-3 ${selected === name ? 'border-accent' : ''}`}>
        <Link className="linka font-semibold" to={`/policy?view=picker&picker_type=${name}`}>{picker.title}</Link>
        <div className="text-dim font-mono text-xs">{name}</div>
        <p className="text-sm">{picker.description}</p>
        <div className="text-dim text-xs">{picker.score}</div>
      </Card>
    ))}
  </div>
}
