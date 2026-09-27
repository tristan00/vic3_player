import { useSearchParams } from 'react-router-dom'
import { DataGrid } from '@/components/DataGrid'

export function useScope() {
  const [params, setParams] = useSearchParams()
  const scope = params.get('scope') ?? 'all'
  const set = (v: string) => {
    const next = new URLSearchParams(params)
    if (v && v !== 'all') next.set('scope', v)
    else next.delete('scope')
    setParams(next, { replace: true })
  }
  return { scope, set }
}

export function ScopeInput() {
  const { scope, set } = useScope()
  return (
    <label className="flex items-center gap-1.5 text-xs">
      <span className="text-dim">scope</span>
      <input
        defaultValue={scope}
        key={scope}
        placeholder="all | run:N | round:N"
        onKeyDown={(e) => e.key === 'Enter' && set((e.target as HTMLInputElement).value.trim())}
        onBlur={(e) => e.target.value.trim() !== scope && set(e.target.value.trim())}
        className="border-line num w-44 rounded border px-1.5 py-0.5"
      />
    </label>
  )
}

export function Actions() {
  const { scope } = useScope()
  return <DataGrid id="stats" url="/api/actions" query={{ scope }} limit={500} toolbar={<ScopeInput />} />
}
