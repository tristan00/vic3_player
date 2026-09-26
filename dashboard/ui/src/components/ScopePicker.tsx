import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { cn } from '@/lib/format'

export function useScope(): string {
  const [params] = useSearchParams()
  return params.get('scope') ?? 'all'
}

export function ScopePicker() {
  const [params, setParams] = useSearchParams()
  const scope = params.get('scope') ?? 'all'
  const [kind, value] = scope === 'all' ? ['all', ''] : scope.split(':')
  const [draft, setDraft] = useState(value)
  const apply = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    if (k === 'all') next.delete('scope')
    else if (v) next.set('scope', `${k}:${v}`)
    else return
    setParams(next, { replace: true })
  }
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <div className="bg-raised flex gap-0.5 rounded-md p-0.5">
        {[
          ['all', 'finished runs'],
          ['round', 'one round'],
          ['run', 'one run'],
        ].map(([k, text]) => (
          <button key={k} onClick={() => (k === 'all' ? apply('all', '') : apply(k, draft))} className={cn('rounded px-2.5 py-1', kind === k ? 'bg-surface font-semibold shadow-sm' : 'text-dim hover:text-fg')}>
            {text}
          </button>
        ))}
      </div>
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value.replace(/\D/g, ''))}
        onKeyDown={(e) => e.key === 'Enter' && apply(kind === 'all' ? 'run' : kind, draft)}
        placeholder="round seed or run id"
        className="border-line num w-44 rounded-md border px-2 py-1"
      />
    </div>
  )
}
