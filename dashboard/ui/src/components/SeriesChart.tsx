import { X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { LineChart } from '@/components/charts'
import { Card, ErrorState } from '@/components/primitives'
import { qs, useApi, type Series } from '@/lib/api'
import { compact, HOURS_PER_YEAR } from '@/lib/format'

const YEAR_OFFSET = 5000

export function yearOf(hours: number): string {
  return (hours / HOURS_PER_YEAR - YEAR_OFFSET).toFixed(1)
}

export function SeriesChart({ run, table, column, filters = [], player = false, title, onRemove }: { run: number; table: string; column: string; filters?: string[]; player?: boolean; title?: string; onRemove?: () => void }) {
  const navigate = useNavigate()
  const state = useApi<Series>(`/api/runs/${run}/series${qs({ table, column, f: filters, player })}`)
  const s = state.data
  const byDate = s?.x === 'game_hours'
  return (
    <Card className="min-w-0 px-3 pt-2 pb-1">
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="num truncate">{title ?? `${table}.${column}`}</span>
        {onRemove && (
          <button className="text-dim hover:text-fg" onClick={onRemove} aria-label={`remove ${table}.${column}`}>
            <X className="size-3" />
          </button>
        )}
      </div>
      {state.error ? (
        <ErrorState error={state.error} onRetry={state.reload} />
      ) : !s ? (
        <div className="bg-raised h-[130px] animate-pulse" />
      ) : (
        <LineChart
          xs={s.xs}
          ys={s.values}
          step={byDate}
          height={130}
          xFormat={byDate ? yearOf : (x) => `#${compact(x)}`}
          tip={(i) => `${s.hours[i] === null ? '' : `${yearOf(s.hours[i] as number)} · `}snapshot ${s.seqs[i]}${byDate ? '' : ` · sample ${s.xs[i]}`}`}
          onPick={(i) => navigate(`/runs/${run}/snapshots/${s.seqs[i]}`)}
        />
      )}
    </Card>
  )
}
