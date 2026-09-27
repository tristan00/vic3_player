import { useSearchParams } from 'react-router-dom'
import { Toggle } from '@/components/primitives'

export function useAsOf() {
  const [params, setParams] = useSearchParams()
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    if (v) next.set(k, v)
    else next.delete(k)
    setParams(next, { replace: true })
  }
  return { seq: params.get('seq') ?? '', versions: params.get('versions') === '1', gone: params.get('gone') === '1', set }
}

export function AsOf({ versions, gone }: { versions?: boolean; gone?: boolean }) {
  const a = useAsOf()
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs">
      <label className="flex items-center gap-1.5">
        <span className="text-dim">snapshot</span>
        <input
          type="number"
          min={0}
          defaultValue={a.seq}
          key={a.seq}
          placeholder="latest"
          onKeyDown={(e) => e.key === 'Enter' && a.set('seq', (e.target as HTMLInputElement).value)}
          onBlur={(e) => e.target.value !== a.seq && a.set('seq', e.target.value)}
          className="border-line num w-20 rounded border px-1.5 py-0.5"
        />
      </label>
      {versions && (
        <Toggle on={a.versions} onChange={(v) => a.set('versions', v ? '1' : '')}>
          every version
        </Toggle>
      )}
      {gone && (
        <Toggle on={a.gone} onChange={(v) => a.set('gone', v ? '1' : '')}>
          include gone
        </Toggle>
      )}
    </div>
  )
}
