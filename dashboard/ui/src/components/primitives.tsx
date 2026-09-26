import type { ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { Cell, Count, LiveState, Rate, Ref, Scope, Status, StatusCount } from '@/lib/api'
import { cn, compact, n, pct, STATUS_FILL, STATUS_HELP, STATUS_LABEL } from '@/lib/format'

export function Section({ title, scope, right, children, className }: { title: string; scope?: Scope; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn('min-w-0', className)}>
      <header className="mb-2 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold tracking-tight">{title}</h2>
          {scope && (
            <p className="text-dim text-2xs">
              {scope.text}
              {scope.detail && <span className="ml-1.5 opacity-80">· {scope.detail}</span>}
            </p>
          )}
        </div>
        {right && <div className="shrink-0">{right}</div>}
      </header>
      {children}
    </section>
  )
}

export function Card({ children, className }: { children?: ReactNode; className?: string }) {
  return <div className={cn('bg-surface border-line rounded-lg border', className)}>{children}</div>
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="text-dim text-2xs font-medium tracking-wide uppercase">{children}</div>
}

export function Tile({ label, value, sub, children }: { label: string; value: ReactNode; sub?: ReactNode; children?: ReactNode }) {
  return (
    <Card className="min-w-0 px-3.5 py-3">
      <Eyebrow>{label}</Eyebrow>
      <div className="mt-0.5 truncate text-xl leading-tight font-semibold">{value}</div>
      {sub && <div className="text-dim text-2xs mt-1">{sub}</div>}
      {children}
    </Card>
  )
}

export function CountText({ count }: { count: Count }) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <b className="num font-semibold">{n(count.value)}</b>
      <span>{count.noun}</span>
      <span className="text-dim text-2xs">{count.population}</span>
    </span>
  )
}

export function RateText({ rate }: { rate: Rate }) {
  const p = pct(rate)
  if (p === null) return <span className="text-dim" title={`no ${rate.population} yet`}>—</span>
  return (
    <span className="num whitespace-nowrap" title={`${rate.noun} of ${rate.population}`}>
      {p} <span className="text-dim text-2xs">{n(rate.n)}/{n(rate.of)}</span>
    </span>
  )
}

export function Swatch({ color, shape = 'dot' }: { color: string; shape?: 'dot' | 'line' | 'box' }) {
  if (shape === 'line') return <span className="inline-block h-0.5 w-3 shrink-0 rounded-full" style={{ background: color }} />
  return <span className={cn('inline-block size-2 shrink-0', shape === 'dot' ? 'rounded-full' : 'rounded-sm')} style={{ background: color }} />
}

export function StatusChip({ status }: { status: Status }) {
  return (
    <span title={STATUS_HELP[status]} className="bg-raised inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-2xs font-medium whitespace-nowrap">
      <Swatch color={STATUS_FILL[status]} />
      {STATUS_LABEL[status]}
    </span>
  )
}

const STATE_STYLE: Record<LiveState, { cls: string; color: string; help: string }> = {
  running: { cls: 'bg-ok-soft', color: 'var(--done)', help: 'the loop is beating and making progress' },
  stalled: { cls: 'bg-warn-soft', color: 'var(--raced)', help: 'the heartbeat is fresh but the current step has not progressed within the stall limit' },
  lost: { cls: 'bg-bad-soft', color: 'var(--invalid)', help: 'the run has no end but its heartbeat stopped; the loop died without ending it' },
  ended: { cls: 'bg-raised', color: 'var(--muted)', help: 'the run has ended' },
}

export function StateChip({ state }: { state: LiveState }) {
  const s = STATE_STYLE[state]
  return (
    <span title={s.help} className={cn('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-2xs font-medium whitespace-nowrap', s.cls)}>
      <Swatch color={s.color} />
      {state}
    </span>
  )
}

export function EndChip({ reason }: { reason: string | null }) {
  if (!reason) return <span className="text-dim">—</span>
  const good = reason === 'time' || reason === 'years'
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-2xs font-medium whitespace-nowrap', good ? 'bg-raised' : 'bg-bad-soft')}>
      <Swatch color={good ? 'var(--muted)' : 'var(--invalid)'} />
      {reason.replaceAll('_', ' ')}
    </span>
  )
}

export function RefLink({ run, refd }: { run: number; refd: Ref }) {
  return (
    <Link to={`/runs/${run}/entities/${refd.kind}/${refd.id}`} className="linka whitespace-nowrap" title={`${refd.kind} ${refd.id}`} onClick={(e) => e.stopPropagation()}>
      {refd.label ?? `${refd.kind.replaceAll('_', ' ')} ${refd.id}`}
    </Link>
  )
}

export function CellView({ run, cell }: { run: number; cell: Cell }) {
  if (cell.ref) return <RefLink run={run} refd={cell.ref} />
  if (cell.text !== null && cell.text !== undefined) return <span className="whitespace-nowrap">{cell.text}</span>
  if (cell.num !== null && cell.num !== undefined) return <span className="num whitespace-nowrap" title={String(cell.num)}>{compact(cell.num)}</span>
  return <span className="text-muted">∅</span>
}

export function cellText(cell: Cell): string {
  if (cell.ref) return cell.ref.label ?? `${cell.ref.kind} ${cell.ref.id}`
  if (cell.text !== null && cell.text !== undefined) return cell.text
  if (cell.num !== null && cell.num !== undefined) return String(cell.num)
  return '∅'
}

export function EmptyState({ what, why }: { what: string; why?: string }) {
  return (
    <Card className="text-dim px-4 py-8 text-center">
      <div className="text-sm">{what}</div>
      {why && <div className="text-2xs mt-1 opacity-80">{why}</div>}
    </Card>
  )
}

export function ErrorState({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <Card className="border-invalid px-4 py-6">
      <div className="text-sm font-medium">this view could not load</div>
      <div className="text-dim text-2xs mt-1">{error}</div>
      {onRetry && (
        <button onClick={onRetry} className="border-line mt-3 rounded border px-2 py-1 text-2xs">
          try again
        </button>
      )}
    </Card>
  )
}

export function Skeleton({ rows = 6 }: { rows?: number }) {
  return (
    <Card className="divide-line divide-y">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="px-3 py-2.5">
          <div className="bg-raised h-3 animate-pulse rounded" style={{ width: `${90 - i * 7}%` }} />
        </div>
      ))}
    </Card>
  )
}

export function Loading<T>({ state, rows, children }: { state: { data: T | null; error: string | null; stale: boolean; reload: () => void }; rows?: number; children: (data: T) => ReactNode }) {
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />
  if (!state.data) return <Skeleton rows={rows} />
  return <div className={cn(state.stale && 'stale')}>{children(state.data)}</div>
}

export function Tabs({ views, param = 'view' }: { views: { key: string; label: string; title?: string }[]; param?: string }) {
  const [params, setParams] = useSearchParams()
  const active = params.get(param) ?? views[0].key
  return (
    <div className="border-line mb-5 flex flex-wrap gap-1 border-b pb-2">
      {views.map((v) => (
        <button
          key={v.key}
          title={v.title}
          onClick={() => {
            const next = new URLSearchParams()
            if (v.key !== views[0].key) next.set(param, v.key)
            setParams(next)
          }}
          className={cn('rounded-md px-2.5 py-1 text-xs', active === v.key ? 'bg-raised text-fg font-semibold' : 'text-dim hover:text-fg')}
        >
          {v.label}
        </button>
      ))}
    </div>
  )
}

export function useTab(views: { key: string }[], param = 'view') {
  const [params] = useSearchParams()
  return params.get(param) ?? views[0].key
}

export function Select({ value, onChange, options, all }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; all: string }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className="border-line rounded-md border px-2 py-1 text-xs">
      <option value="">{all}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

export function Pager({ offset, limit, shown, total, onOffset }: { offset: number; limit: number; shown: number; total: number; onOffset: (o: number) => void }) {
  return (
    <div className="flex items-center gap-1.5">
      <button disabled={offset <= 0} onClick={() => onOffset(Math.max(0, offset - limit))} className="border-line bg-surface rounded-md border px-2 py-0.5 text-2xs">
        newer
      </button>
      <span className="text-dim num text-2xs whitespace-nowrap">
        {total ? `${n(offset + 1)}–${n(offset + shown)}` : '0'} of {n(total)}
      </span>
      <button disabled={offset + shown >= total} onClick={() => onOffset(offset + limit)} className="border-line bg-surface rounded-md border px-2 py-0.5 text-2xs">
        older
      </button>
    </div>
  )
}

export function KV({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-xs">
      {items.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-dim">{k}</dt>
          <dd className="min-w-0 truncate">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function statusTotal(counts: StatusCount[]): number {
  return counts.reduce((a, c) => a + c.count, 0)
}
