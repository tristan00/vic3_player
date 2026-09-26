import { useNavigate } from 'react-router-dom'
import { LineChart } from '@/components/charts'
import { Card, ErrorState } from '@/components/primitives'
import { useApi, type Series } from '@/lib/api'
import { compact, HOURS_PER_YEAR } from '@/lib/format'

const YEAR_OFFSET = 5000

export function yearOf(hours: number): string {
  return (hours / HOURS_PER_YEAR - YEAR_OFFSET).toFixed(1)
}

export function SeriesView({ run, series, height = 130, onRemove }: { run: number; series: Series; height?: number; onRemove?: () => void }) {
  const navigate = useNavigate()
  const byDate = series.x === 'game_hours'
  const last = series.values.length ? series.values[series.values.length - 1] : null
  return (
    <Card className="min-w-0 px-3 pt-2.5 pb-1">
      <div className="flex items-baseline justify-between gap-2">
        <div className="min-w-0 truncate text-xs" title={series.scope.text + (series.scope.detail ? ` · ${series.scope.detail}` : '')}>
          <span className="font-medium">{series.title}</span> <span className="text-dim text-2xs">{series.table}</span>
        </div>
        <div className="flex shrink-0 items-baseline gap-2">
          {last !== null && <span className="num text-xs font-semibold">{compact(last)}</span>}
          {onRemove && (
            <button className="text-dim hover:text-fg text-2xs" onClick={onRemove} aria-label={`remove ${series.label}`}>
              ✕
            </button>
          )}
        </div>
      </div>
      <LineChart
        xs={series.xs}
        ys={series.values}
        step={byDate}
        height={height}
        xFormat={byDate ? yearOf : (x) => `#${compact(x)}`}
        tip={(i) => {
          const h = series.hours[i]
          const where = h === null ? `sample ${series.xs[i]}` : byDate ? `snapshot ${series.seqs[i]}` : `sample ${series.xs[i]}`
          return `${h === null ? '' : `${yearOf(h)} · `}${where}`
        }}
        onPick={byDate ? (i) => navigate(`/runs/${run}/snapshots/${series.seqs[i]}`) : undefined}
        empty="no value recorded"
      />
    </Card>
  )
}

export function SeriesChart({ run, table, column, onRemove }: { run: number; table: string; column: string; onRemove?: () => void }) {
  const state = useApi<Series>(`/api/runs/${run}/series?table=${table}&column=${column}`)
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />
  if (!state.data) return <Card className="h-[170px] animate-pulse" />
  return <SeriesView run={run} series={state.data} onRemove={onRemove} />
}
