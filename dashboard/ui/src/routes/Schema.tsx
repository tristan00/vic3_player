import { ChevronDown, ChevronRight } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Card, Loading, Section } from '@/components/primitives'
import { Table, type Col } from '@/components/Table'
import { useApi, type S } from '@/lib/api'
import { cn, label, n } from '@/lib/format'

const KIND_HELP: Record<string, string> = {
  history: 'one row per entity, versioned: a new row whenever any column changes, and a gone row when the entity disappears',
  subject: 'one row per present entity, stored again only when a value changes',
  child: 'keyed rows under an entity, versioned like history',
  listing: 'keyed rows with no owning entity, versioned like history',
  sample: 'trend buffers the game keeps; each sample is stored once',
  singleton: 'one row about the player, stored again only when a value changes',
}

function Columns({ t }: { t: S['SchemaTable'] }) {
  const all = [...t.keys.map((c) => ({ ...c, key: true })), ...t.columns.map((c) => ({ ...c, key: false }))]
  return (
    <table className="w-full text-xs">
      <tbody>
        {all.map((c) => (
          <tr key={c.name} className="border-line/60 border-b last:border-0">
            <td className="px-3 py-1">
              <code className={cn(c.key && 'font-semibold')}>{c.name}</code>
              {c.key && <span className="text-dim ml-1 text-2xs">key</span>}
            </td>
            <td className="text-dim px-3 py-1">{c.kind}</td>
            <td className="px-3 py-1">{c.target ? <code className="text-2xs">{c.target}</code> : <span className="text-muted">{c.type}</span>}</td>
            <td className="text-dim px-3 py-1 text-2xs">{c.optional ? 'nullable' : ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function Schema() {
  const state = useApi<S['SchemaPage']>('/api/schema')
  const [filter, setFilter] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  return (
    <Loading state={state} rows={14}>
      {(d) => <SchemaBody d={d} filter={filter} setFilter={setFilter} open={open} setOpen={setOpen} />}
    </Loading>
  )
}

function SchemaBody({ d, filter, setFilter, open, setOpen }: { d: S['SchemaPage']; filter: string; setFilter: (v: string) => void; open: string | null; setOpen: (v: string | null) => void }) {
  const byOwner = useMemo(() => {
    const groups = new Map<string, S['SchemaTable'][]>()
    for (const t of d.tables) {
      if (filter && !t.name.includes(filter) && !t.columns.some((c) => c.name.includes(filter))) continue
      const owner = t.owner ?? (t.scope === 'player' ? 'the player' : 'the world')
      groups.set(owner, [...(groups.get(owner) ?? []), t])
    }
    return [...groups.entries()]
  }, [d, filter])
  const gapCols: Col<S['CaptureGap']>[] = [
    { key: 'kind', label: 'kind', value: (g) => g.kind, render: (g) => label(g.kind) },
    { key: 'subject', label: 'subject', value: (g) => g.subject, render: (g) => <code className="text-2xs">{g.subject}</code> },
    { key: 'detail', label: 'detail', value: (g) => g.detail, render: (g) => <span className="text-2xs">{g.detail}</span> },
  ]
  return (
    <div className="space-y-8">
      <Section title="what the recorder stores" scope={{ text: `${n(d.tables.length)} tables about ${n(d.entities.length)} kinds of entity`, detail: 'generated from interface/recording/spec.py' }}>
        <div className="mb-3 grid gap-2 md:grid-cols-3">
          {Object.entries(KIND_HELP).map(([k, v]) => (
            <Card key={k} className="px-3 py-2 text-2xs">
              <b className="text-xs">{k}</b> <span className="text-dim">{n(d.tables.filter((t) => t.kind === k).length)} tables</span>
              <div className="text-dim mt-0.5">{v}</div>
            </Card>
          ))}
        </div>
        <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="filter by table or column…" className="border-line mb-3 w-full max-w-sm rounded-md border px-2 py-1 text-xs" />
        <div className="space-y-4">
          {byOwner.map(([owner, tables]) => (
            <div key={owner}>
              <h3 className="mb-1 text-sm font-semibold">{label(owner)}</h3>
              <Card className="divide-line divide-y overflow-hidden">
                {tables.map((t) => (
                  <div key={t.name}>
                    <button className="hover:bg-raised flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs" onClick={() => setOpen(open === t.name ? null : t.name)}>
                      {open === t.name ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
                      <code className="font-medium">{t.name}</code>
                      <span className="text-dim text-2xs" title={KIND_HELP[t.kind]}>
                        {t.kind}
                      </span>
                      <span className="text-dim ml-auto text-2xs">{n(t.keys.length + t.columns.length)} columns</span>
                    </button>
                    {open === t.name && (
                      <div className="bg-bg border-line border-t">
                        <Columns t={t} />
                      </div>
                    )}
                  </div>
                ))}
              </Card>
            </div>
          ))}
        </div>
      </Section>
      <Section title="capture gaps" scope={{ text: d.ruleset_id ? `what the recorder could not evaluate in ruleset ${d.ruleset_id}, the ruleset of the newest run` : 'no run recorded yet' }}>
        <Table rows={d.gaps} cols={gapCols} rowKey={(g, i) => `${g.kind}.${g.subject}.${i}`} empty="no gap recorded" maxHeight={560} />
      </Section>
    </div>
  )
}
