import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { cn, label } from '@/lib/format'

export function Section({ title, right, children, className }: { title: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn('min-w-0', className)}>
      <header className="mb-1.5 flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-base font-semibold">{typeof title === 'string' ? label(title) : title}</h2>
        {right && <div className="shrink-0">{right}</div>}
      </header>
      {children}
    </section>
  )
}

export function Card({ children, className }: { children?: ReactNode; className?: string }) {
  return <div className={cn('bg-surface border-line rounded-md border', className)}>{children}</div>
}

export function ErrorState({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <Card className="border-invalid px-3 py-2 text-xs">
      <span>{error}</span>
      {onRetry && (
        <button onClick={onRetry} className="border-line ml-3 rounded border px-2 py-0.5 text-2xs">
          retry
        </button>
      )}
    </Card>
  )
}

export function Loading<T>({ state, children }: { state: { data: T | null; error: string | null; stale: boolean; reload: () => void }; children: (data: T) => ReactNode }) {
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />
  if (!state.data) return <Card className="bg-raised h-16 animate-pulse" />
  return <div className={cn(state.stale && 'stale')}>{children(state.data)}</div>
}

export function Tabs({ views, param = 'view', labels = {} }: { views: string[]; param?: string; labels?: Record<string, string> }) {
  const [params, setParams] = useSearchParams()
  const active = useTab(views, param)
  return (
    <div className="border-line mb-4 flex flex-wrap gap-1 border-b pb-1.5">
      {views.map((v) => (
        <button
          key={v}
          onClick={() => {
            const next = new URLSearchParams(params)
            next.delete(param)
            if (v !== views[0]) next.set(param, v)
            setParams(next)
          }}
          aria-current={active === v ? 'page' : undefined}
          className={cn('rounded px-3 py-2 text-sm capitalize', active === v ? 'bg-accent-soft text-accent font-semibold' : 'text-dim hover:text-fg hover:bg-raised')}
        >
          {labels[v] ?? label(v)}
        </button>
      ))}
    </div>
  )
}

export function useTab(views: string[], param = 'view') {
  const [params] = useSearchParams()
  const requested = params.get(param)
  return requested && views.includes(requested) ? requested : views[0]
}

export function Toggle({ on, onChange, children }: { on: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center gap-1.5 text-xs">
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} />
      {children}
    </label>
  )
}
