import { useState, type ReactNode } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Card, Loading, Section, Tabs, useTab } from '@/components/primitives'
import { useApi } from '@/lib/api'

type Run = { run_id: number; country: string; player_country: number; status: string; end_reason: string | null; started_at: string; heartbeat_at: string; progress_step: string; picker: string; snapshot: number | null; snapshots: number; actions: number }
type World = { key: string; world_id: number | null; name: string; seed: number | null; status: string; issue: string | null; countries: number | null; states: number | null; sources: string[]; runs: Run[]; local: boolean; provenance: boolean }
type Country = { tag: string; name: string; source?: string; copy?: string; country_type: string; capital: string; culture: string; cultures?: string[]; ideology_uniformity?: number; primary_culture_share?: number; tech_count: number; technologies?: string[]; states: string[]; entity: number | null }
type State = { key: string; name: string; country: string; template?: string; source_region?: string; economic_scale?: number; provinces: string[]; coastal: boolean; entities: number[]; population: number | null; levels: number | null; arable: number | null; traits: string[]; arable_resources: string[]; resources: { type: string; amount: string; kind: string }[]; homelands: string[]; definition_available: boolean; pops: { culture: string; religion: string | null; pop_type: string | null; size: string }[] | null; buildings: { type: string; levels: number; methods: string[] }[] | null }
type Detail = Omit<World, 'countries' | 'states'> & { countries: Country[]; states: State[]; selected_run: number | null; content_issue: string | null; directory: string | null; manifest: Record<string, unknown>; audit: { totals: Record<string, number>; states: { state: string; source_population: number; population: number; source_levels: number; levels: number; source_arable: number; arable: number }[] } | null }
const number = (v: number | null | undefined) => v == null ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: 2 })
const name = (v: string) => v.replace(/^(STATE_|region_|building_|state_trait_|pm_)/, '').replaceAll('_', ' ')
const date = (v: string) => new Date(v).toLocaleString()

function Badge({ children }: { children: ReactNode }) {
  const color = children === 'running' ? 'var(--done)' : ['lost', 'stalled', 'Incomplete'].includes(String(children)) ? 'var(--invalid)' : undefined
  return <span style={{ color }} className="bg-raised text-dim inline-flex rounded px-1.5 py-0.5 text-xs">{children}</span>
}

function Table({ headers, children }: { headers: string[]; children: ReactNode }) {
  return <div className="border-line overflow-x-auto rounded-md border"><table className="world-table w-full text-left text-xs"><thead className="bg-raised text-dim"><tr>{headers.map(h => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead><tbody className="bg-surface">{children}</tbody></table></div>
}

function Metrics({ items }: { items: [string, ReactNode][] }) {
  return <dl className="border-line flex flex-wrap gap-x-8 gap-y-2 border-y py-2.5 text-xs">{items.map(([label, value]) => <div key={label} className="flex items-baseline gap-2"><dt className="text-dim">{label}</dt><dd className="num font-semibold">{value}</dd></div>)}</dl>
}

export function Worlds() {
  const state = useApi<World[]>('/api/worlds', { live: true })
  const [search, setSearch] = useSearchParams()
  const query = search.get('q') ?? ''
  const status = search.get('status') ?? 'All'
  const set = (key: string, value: string) => { const next = new URLSearchParams(search); next.set(key, value); setSearch(next, { replace: true }) }
  return <div className="space-y-3">
    <div className="flex items-start justify-between gap-4"><div><h1 className="text-base font-semibold">Worlds</h1></div><button className="border-line rounded border px-2 py-1 text-xs" onClick={state.reload}>Refresh</button></div>
    <Loading state={state}>{worlds => {
      const shown = worlds.filter(w => (status === 'All' || w.status === status) && `${w.name} ${w.seed} ${w.sources.join(' ')}`.toLowerCase().includes(query.toLowerCase()))
      return <div className="space-y-4">
        <Metrics items={[["Worlds", worlds.length], ["Unrun", worlds.filter(w => w.status === 'Generated').length], ["Recorded", worlds.filter(w => w.runs.length).length], ["Incomplete", worlds.filter(w => w.status === 'Incomplete').length]]} />
        <div className="flex flex-wrap items-center gap-3"><input aria-label="Search worlds" className="bg-surface border-line min-w-64 rounded border px-2 py-1 text-xs" placeholder="World, seed, region…" value={query} onChange={e => set('q', e.target.value)} /><select aria-label="Generation status" className="border-line rounded border px-2 py-1 text-xs" value={status} onChange={e => set('status', e.target.value)}>{['All', 'Generated', 'Recorded', 'Registered', 'Incomplete'].map(s => <option key={s}>{s}</option>)}</select><span className="text-dim text-xs">{shown.length} worlds</span></div>
        <Table headers={['World / seed', 'Status', 'Countries / states', 'Source regions', 'Latest run']}>{shown.map(w => <tr key={w.key}>
          <td><Link className="linka font-semibold" to={`/worlds/${w.key}`}>{w.world_id == null ? `Seed ${w.seed ?? 'unknown'}` : w.name}</Link><div className="text-dim mt-1 text-xs">{w.world_id == null ? 'Local' : `Seed ${w.seed ?? 'not recorded'}`}</div></td>
          <td><Badge>{w.status}</Badge><div className="text-dim mt-1 text-xs">{w.issue ?? (w.local ? 'Local files' : 'Archived map')}</div></td>
          <td className="num">{number(w.countries)} / {number(w.states)}</td>
          <td>{w.sources.length ? w.sources.map(name).join(', ') : '—'}</td>
          <td>{w.runs.length ? <><Link className="linka" to={`/runs/${w.runs[0].run_id}`}>Run {w.runs[0].run_id}</Link><span className="ml-2 text-xs">{w.runs[0].status}</span><div className="mt-1 text-xs"><Link className="linka" to={`/policy/runs/${w.runs[0].run_id}`}>Policy</Link> · {w.runs.length} runs</div></> : <span className="text-dim">No runs</span>}</td>
        </tr>)}</Table>
        {!shown.length && <Card className="p-3 text-xs">No matches</Card>}
      </div>
    }}</Loading>
  </div>
}

function Runs({ runs }: { runs: Run[] }) {
  if (!runs.length) return <Card className="p-3 text-xs">No runs</Card>
  return <Table headers={['Run / player', 'Status', 'Progress', 'Snapshots / actions', 'Policy', 'Last heartbeat']}>{runs.map(r => <tr key={r.run_id}><td><Link className="linka font-semibold" to={`/runs/${r.run_id}`}>Run {r.run_id}</Link><div><Link className="linka text-xs" to={`/runs/${r.run_id}/entities/country/${r.player_country}`}>{r.country}</Link></div></td><td><Badge>{r.status}</Badge><div className="text-dim text-xs">{r.end_reason}</div></td><td>{r.progress_step}<div className="text-dim text-xs">Started {date(r.started_at)}</div></td><td>{r.snapshot != null && <Link className="linka" to={`/runs/${r.run_id}/snapshots/${r.snapshot}`}>Snapshot {r.snapshot}</Link>}<div className="text-dim text-xs">{r.snapshots} snapshots · {r.actions} actions</div></td><td><Link className="linka" to={`/policy/runs/${r.run_id}`}>Policy</Link><div className="text-dim text-xs">{r.picker} picker</div></td><td className="text-xs">{date(r.heartbeat_at)}</td></tr>)}</Table>
}

function StateDetail({ state: s, world: w }: { state: State; world: Detail }) {
  const before = w.audit?.states.find(a => a.state === s.key)
  return <div className="space-y-3">
    <Card className="space-y-3 p-3"><div className="flex flex-wrap items-center gap-3"><h2 className="text-lg font-semibold">{s.name}</h2><Badge>{s.coastal ? 'Coastal' : 'Inland'}</Badge>{s.entities.map(id => <span key={id} className="flex gap-3 text-sm"><Link className="linka" to={`/runs/${w.selected_run}/entities/state/${id}`}>State #{id}</Link><Link className="linka" to={`/runs/${w.selected_run}/entities/building?e.f=state:${id}`}>Buildings</Link><Link className="linka" to={`/runs/${w.selected_run}/entities/pop?e.f=location:${id}`}>Pops</Link></span>)}</div><div className="text-dim text-xs">{s.key} · {s.country}</div><dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs lg:grid-cols-4">{[['Source state', s.template ? name(s.template) : '—'], ['Source region', s.source_region ? name(s.source_region) : '—'], ['Provinces', s.provinces.length], ['Province origins', 'Not saved'], ['Economic scale', s.economic_scale == null ? '—' : `${number(s.economic_scale)}×`], ['Homelands', s.homelands.map(name).join(', ') || '—']].map(([label, value]) => <div key={label}><dt className="text-dim">{label}</dt><dd>{value}</dd></div>)}</dl></Card>
    {before && <Section title="Source comparison"><Table headers={['Measure', 'Source', 'Generated', 'Change']}>{[['Population', before.source_population, before.population], ['Owned building levels', before.source_levels, before.levels], ['Arable land', before.source_arable, before.arable]].map(([label, a, b]) => <tr key={label}><td>{label}</td><td>{number(Number(a))}</td><td>{number(Number(b))}</td><td>{number(Number(b) - Number(a))}</td></tr>)}</Table></Section>}
    <div className="grid gap-5 lg:grid-cols-2"><Section title="Resources / modifiers"><Card className="space-y-3 p-3 text-xs">{s.definition_available ? <><div>Arable land: <strong>{number(s.arable)}</strong></div><div><span className="text-dim">Traits</span><p>{s.traits.length ? s.traits.map(name).join(', ') : 'None'}</p></div><div><span className="text-dim">Arable resources</span><p>{s.arable_resources.map(name).join(', ') || 'None'}</p></div>{s.resources.map((r, i) => <div key={i} className="flex justify-between gap-4"><span>{name(r.type)}</span><span>{r.amount} · {r.kind}</span></div>)}</> : 'Definition unavailable'}</Card></Section><Section title="Provinces"><Card className="max-h-64 overflow-auto p-3"><div className="flex flex-wrap gap-2">{s.provinces.map(p => <span key={p} className="bg-raised rounded px-2 py-1 font-mono text-xs">{p}</span>)}</div></Card></Section></div>
    <Section title={`Starting buildings · ${number(s.levels)} levels`}>{s.buildings == null ? <Card className="p-3 text-xs">History unavailable</Card> : s.buildings.length === 0 ? <Card className="p-3 text-xs">None</Card> : <Table headers={['Building', 'Levels', 'Production methods']}>{s.buildings.map((b, i) => <tr key={i}><td>{name(b.type)}</td><td>{number(b.levels)}</td><td>{b.methods.map(name).join(', ') || 'Default'}</td></tr>)}</Table>}</Section>
    <Section title={`Starting population · ${number(s.population)}`}>{s.pops == null ? <Card className="p-3 text-xs">History unavailable</Card> : s.pops.length === 0 ? <Card className="p-3 text-xs">None</Card> : <Table headers={['Culture', 'Religion', 'Profession', 'People']}>{s.pops.map((p, i) => <tr key={i}><td>{p.culture}</td><td>{p.religion ?? 'Default'}</td><td>{p.pop_type ?? 'Default'}</td><td>{number(Number(p.size))}</td></tr>)}</Table>}</Section>
  </div>
}

export function WorldDetail() {
  const { world } = useParams()
  const [params, setParams] = useSearchParams()
  const run = params.get('run')
  const state = useApi<Detail>(`/api/worlds/${world}${run ? `?run=${run}` : ''}`, { live: true })
  const view = useTab(['overview', 'countries', 'states', 'settings'])
  const [filter, setFilter] = useState('')
  const selected = params.get('state')
  const country = params.get('country')
  const change = (values: Record<string, string | null>) => { const next = new URLSearchParams(params); Object.entries(values).forEach(([k, v]) => v == null ? next.delete(k) : next.set(k, v)); setParams(next) }
  return <div className="space-y-3"><Link className="linka text-sm" to="/worlds">Worlds</Link><Loading state={state}>{w => {
    const s = w.states.find(s => s.key === selected)
    const total = (key: 'population' | 'levels') => w.states.length && w.states.every(s => s[key] != null) ? w.states.reduce((n, s) => n + s[key]!, 0) : null
    return <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-3"><h1 className="text-base font-semibold">{w.world_id == null ? `Seed ${w.seed ?? 'unknown'}` : `World ${w.world_id}`}</h1><Badge>{w.status}</Badge></div><p className="text-dim mt-2 text-sm">Seed {w.seed ?? 'not recorded'} · {w.sources.map(name).join(', ') || 'Source regions not recorded'}</p></div>{w.runs.length > 0 && <label className="text-dim text-xs">Run<select aria-label="Entity run" className="border-line ml-2 rounded border px-3 py-2" value={w.selected_run ?? ''} onChange={e => change({ run: e.target.value })}>{w.runs.map(r => <option key={r.run_id} value={r.run_id}>Run {r.run_id} · {r.country} · {r.status}</option>)}</select></label>}</div>
      {(w.issue || w.content_issue) && <Card className="border-invalid p-3 text-xs">{w.issue ?? w.content_issue}</Card>}
      <Metrics items={[["Countries / states", `${w.countries.length} / ${w.states.length}`], ["Initial population", number(total('population'))], ["Initial levels", number(total('levels'))], ["Runs", w.runs.length], ["Provinces", w.states.reduce((n, s) => n + s.provinces.length, 0)], ["Coastal states", w.states.filter(s => s.coastal).length]]} />
      <Tabs views={['overview', 'countries', 'states', 'settings']} />
      {view === 'overview' && <div className="space-y-4"><Section title="Runs"><Runs runs={w.runs} /></Section><Section title="Countries"><Table headers={['Country', 'Source', 'States', 'Initial population', 'Initial levels', 'Capital', 'Entity']}>{w.countries.map(c => {
        const states = w.states.filter(s => s.country === c.tag)
        const sum = (key: 'population' | 'levels') => states.length && states.every(s => s[key] != null) ? states.reduce((n, s) => n + s[key]!, 0) : null
        return <tr key={c.tag}><td><button className="linka font-semibold" onClick={() => change({ view: 'states', country: c.tag, state: null })}>{c.name}</button>{c.name !== c.tag && <span className="text-dim ml-2">{c.tag}</span>}</td><td>{c.source ?? '—'}</td><td><button className="linka num" onClick={() => change({ view: 'states', country: c.tag, state: null })}>{states.length}</button></td><td className="num">{number(sum('population'))}</td><td className="num">{number(sum('levels'))}</td><td><button className="linka" onClick={() => change({ view: 'states', country: null, state: c.capital })}>{w.states.find(s => s.key === c.capital)?.name ?? c.capital}</button></td><td>{c.entity != null ? <Link className="linka" to={`/runs/${w.selected_run}/entities/country/${c.entity}`}>#{c.entity}</Link> : '—'}</td></tr>
      })}</Table></Section>{w.selected_run != null && <nav aria-label="World entities" className="border-line flex flex-wrap gap-4 border-t pt-3 text-xs">{['country', 'state', 'province', 'pop', 'building', 'market', 'law', 'country_research'].map(k => <Link key={k} className="linka capitalize" to={`/runs/${w.selected_run}/entities/${k}`}>{name(k)}</Link>)}</nav>}</div>}
      {view === 'countries' && <Section title="Countries"><Table headers={['Country', 'Origin / type', 'Culture / technology', 'Primary culture share', 'Ideology uniformity', 'States', 'Recorded entity']}>{w.countries.map(c => <tr key={c.tag}><td className="font-semibold">{c.name}<div className="text-dim text-xs">{c.tag}</div></td><td>{c.source ?? 'Not recorded'}<div className="text-dim text-xs">{c.copy ? 'Copied country' : 'Generated country'} · {c.country_type}</div></td><td>{c.cultures?.join(', ') ?? c.culture}<details className="text-xs"><summary className="cursor-pointer">{c.tech_count} technologies</summary><p className="mt-2 max-w-sm">{c.technologies?.map(name).join(', ') ?? 'Unavailable'}</p></details></td><td>{c.primary_culture_share == null ? '—' : `${number(c.primary_culture_share * 100)}%`}</td><td>{c.ideology_uniformity == null ? '—' : `${number(c.ideology_uniformity * 100)}%`}</td><td><button className="linka" onClick={() => change({ view: 'states', country: c.tag, state: null })}>{c.states.length} states</button><div className="text-xs"><button className="linka" onClick={() => change({ view: 'states', country: null, state: c.capital })}>Capital: {w.states.find(s => s.key === c.capital)?.name ?? c.capital}</button></div></td><td>{c.entity != null ? <Link className="linka" to={`/runs/${w.selected_run}/entities/country/${c.entity}`}>Country #{c.entity}</Link> : <span className="text-dim">—</span>}</td></tr>)}</Table></Section>}
      {view === 'states' && <div className="space-y-3"><div className="flex flex-wrap items-center gap-3"><input aria-label="Search states" className="border-line rounded border px-2 py-1 text-xs" placeholder="Search state or source…" value={filter} onChange={e => setFilter(e.target.value)} /><select aria-label="State country" className="border-line rounded border px-2 py-1 text-xs" value={country ?? ''} onChange={e => change({ country: e.target.value || null, state: null })}><option value="">All countries</option>{w.countries.map(c => <option key={c.tag} value={c.tag}>{c.name} · {c.tag}</option>)}</select>{s && <button className="linka text-sm" onClick={() => change({ state: null })}>All states</button>}</div>{s ? <StateDetail state={s} world={w} /> : <Table headers={['State / country', 'Source state / region', 'Population', 'Buildings / arable', 'Geography']}>{w.states.filter(s => (!country || s.country === country) && `${s.name} ${s.key} ${s.template} ${s.source_region}`.toLowerCase().includes(filter.toLowerCase())).map(s => <tr key={s.key}><td><button className="linka font-semibold" onClick={() => change({ state: s.key })}>{s.name}</button><div className="text-dim text-xs">{s.country} · {s.key}</div></td><td>{s.template ? name(s.template) : 'Not recorded'}<div className="text-dim text-xs">{s.source_region ? name(s.source_region) : 'Not recorded'}</div></td><td>{number(s.population)}</td><td>{number(s.levels)} levels<div className="text-dim text-xs">{number(s.arable)} arable</div></td><td>{s.coastal ? 'Coastal' : 'Inland'}<div className="text-dim text-xs">{s.provinces.length} provinces</div></td></tr>)}</Table>}</div>}
      {view === 'settings' && <div className="space-y-3"><Section title="Generation settings"><Table headers={['Setting', 'Value']}>{['seed', 'tech', 'ideology_uniformity', 'primary_culture_share', 'copies', 'tech_variation', 'country_economy', 'local_economy', 'source_regions', 'width', 'height'].map(k => <tr key={k}><td>{name(k)}</td><td>{w.manifest[k] == null ? 'Not recorded' : Array.isArray(w.manifest[k]) ? (w.manifest[k] as number[]).map(v => number(v)).join(' – ') : typeof w.manifest[k] === 'number' ? number(w.manifest[k] as number) : String(w.manifest[k])}</td></tr>)}</Table></Section><Section title="Data"><Table headers={['Record', 'Availability']}><tr><td>Local files</td><td className="break-all">{w.directory ?? 'Unavailable'}</td></tr><tr><td>State origins</td><td>{w.provenance ? 'Saved' : 'Not saved'}</td></tr><tr><td>Province origins</td><td>Not saved</td></tr><tr><td>Source comparison</td><td>{w.audit ? 'Saved' : 'Not saved'}</td></tr></Table></Section></div>}
    </div>
  }}</Loading></div>
}
