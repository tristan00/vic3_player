import { X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { LineChart } from '@/components/charts'
import { Card, ErrorState } from '@/components/primitives'
import { qs, useApi, type Series } from '@/lib/api'
import { compact, HOURS_PER_YEAR, num } from '@/lib/format'

const YEAR_OFFSET = 5000

export function yearOf(hours: number): string {
  return (hours / HOURS_PER_YEAR - YEAR_OFFSET).toFixed(1)
}

export function SeriesView({ run, series, title, onRemove, height = 130 }: { run: number; series: Series | null; title: string; onRemove?: () => void; height?: number }) {
  const navigate = useNavigate()
  const s = series
  const byDate = s?.x === 'game_hours'
  const last = s && s.values.length ? s.values[s.values.length - 1] : null
  return (
    <Card className="min-w-0 px-3 pt-2 pb-1">
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="num truncate">{title}</span>
        <span className="flex items-baseline gap-2">
          {last !== null && <span className="num font-semibold">{num(last)}</span>}
          {onRemove && (
            <button className="text-dim hover:text-fg" onClick={onRemove} aria-label={`remove ${title}`}>
              <X className="size-3" />
            </button>
          )}
        </span>
      </div>
      {!s ? (
        <div className="bg-raised animate-pulse" style={{ height }} />
      ) : (
        <LineChart
          xs={s.xs}
          ys={s.values}
          step={byDate}
          height={height}
          xFormat={byDate ? yearOf : (x) => `#${compact(x)}`}
          tip={(i) => `${s.hours[i] === null ? '' : `${yearOf(s.hours[i] as number)} · `}snapshot ${s.seqs[i]}${byDate ? '' : ` · sample ${s.xs[i]}`}`}
          onPick={(i) => navigate(`/runs/${run}/snapshots/${s.seqs[i]}`)}
        />
      )}
    </Card>
  )
}

export function SeriesChart({ run, table, column, filters = [], player = false, title, onRemove }: { run: number; table: string; column: string; filters?: string[]; player?: boolean; title?: string; onRemove?: () => void }) {
  const state = useApi<Series>(`/api/runs/${run}/series${qs({ table, column, f: filters, player })}`)
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />
  return <SeriesView run={run} series={state.data} title={title ?? `${table}.${column}`} onRemove={onRemove} />
}
