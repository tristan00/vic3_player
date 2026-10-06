import { useSearchParams } from 'react-router-dom'
import { DataGrid } from '@/components/DataGrid'
import { Tabs, useTab } from '@/components/primitives'

const VIEWS = ['commands', 'levers']

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
  const view = useTab(VIEWS)
  return (
    <div className="space-y-4">
      <h1 className="font-semibold">Actions</h1>
      <Tabs views={VIEWS} labels={{ commands: 'Interface commands', levers: 'Levers' }} />
      {view === 'commands' && <><p className="text-dim">Compare action outcomes and timings. Open an action to inspect its runs and entity targets.</p><DataGrid id="stats" url="/api/actions" query={{ scope }} limit={50} toolbar={<ScopeInput />} /></>}
      {view === 'levers' && <><p className="text-dim">A weight is set on a lever, not on a command. Each lever holds one or more acts, and an act is carried out by the interface commands listed beside it. Commands that were never sent are not listed.</p><DataGrid id="levers" url="/api/levers" query={{ scope }} limit={100} toolbar={<ScopeInput />} /></>}
    </div>
  )
}
