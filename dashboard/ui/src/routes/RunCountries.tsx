import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LineChart } from '@/components/charts'
import { Card, Loading, RefLink, Section } from '@/components/primitives'
import { yearOf } from '@/components/SeriesChart'
import { Table, type Col } from '@/components/Table'
import { useApi, type S } from '@/lib/api'
import { compact, n } from '@/lib/format'

type Track = S['CountryTrack']
type Metric = 'states' | 'provinces' | 'population' | 'gdp' | 'exports' | 'imports'

const METRICS: { key: Metric; label: string }[] = [
  { key: 'states', label: 'states' },
  { key: 'provinces', label: 'provinces' },
  { key: 'population', label: 'population' },
  { key: 'gdp', label: 'gdp' },
  { key: 'exports', label: 'exports' },
  { key: 'imports', label: 'imports' },
]

function first(values: (number | null)[]) {
  return values.find((v) => v !== null) ?? null
}

function last(values: (number | null)[]) {
  for (let i = values.length - 1; i >= 0; i--) if (values[i] !== null) return values[i]
  return null
}

function Spark({ values }: { values: (number | null)[] }) {
  const pts = values.map((v, i) => [i, v] as const).filter((p): p is readonly [number, number] => p[1] !== null)
  if (pts.length < 2) return null
  const lo = Math.min(...pts.map((p) => p[1]))
  const hi = Math.max(...pts.map((p) => p[1]))
  const span = hi - lo || 1
  const w = 72
  const h = 18
  const d = pts.map(([i, v], k) => `${k ? 'L' : 'M'}${((i / (values.length - 1)) * w).toFixed(1)},${(h - ((v - lo) / span) * h).toFixed(1)}`).join('')
  return (
    <svg width={w} height={h} className="inline-block align-middle" aria-hidden>
      <path d={d} fill="none" stroke="var(--series)" strokeWidth={1.5} />
    </svg>
  )
}

function Change({ values, percent }: { values: (number | null)[]; percent?: boolean }) {
  const a = first(values)
  const b = last(values)
  if (a === null || b === null) return <span className="text-muted">—</span>
  const diff = b - a
  const text = percent ? (a ? `${diff >= 0 ? '+' : ''}${((100 * diff) / a).toFixed(0)}%` : '') : `${diff >= 0 ? '+' : ''}${compact(diff)}`
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <span className="num">{compact(b)}</span>
      <span className="text-dim num text-2xs">{text}</span>
      <Spark values={values} />
    </span>
  )
}

export function RunCountries({ run }: { run: number }) {
  const state = useApi<S['CountryProgress']>(`/api/runs/${run}/countries`)
  const [picked, setPicked] = useState<number | null>(null)
  const navigate = useNavigate()
  return (
    <Loading state={state} rows={12}>
      {(d) => {
        const chosen = d.countries.find((c) => c.ref.id === picked) ?? d.countries[0]
        const cols: Col<Track>[] = [
          {
            key: 'country',
            label: 'country',
            value: (c) => c.ref.label ?? String(c.ref.id),
            render: (c) => (
              <span className="inline-flex items-center gap-2 whitespace-nowrap">
                <RefLink run={run} refd={c.ref} />
                <span className="text-dim num text-2xs">#{c.ref.id}</span>
                {c.player && <span className="bg-accent-soft rounded-full px-1.5 text-2xs">player</span>}
                {last(c.states) === null && <span className="bg-bad-soft rounded-full px-1.5 text-2xs">gone</span>}
              </span>
            ),
          },
          ...METRICS.map((m) => ({
            key: m.key,
            label: m.label,
            value: (c: Track) => last(c[m.key]),
            render: (c: Track) => <Change values={c[m.key]} percent={m.key === 'population' || m.key === 'gdp'} />,
          })),
        ]
        return (
          <div className="space-y-6">
            <Section title="countries over the run" scope={d.scope}>
              <Table rows={d.countries} cols={cols} rowKey={(c) => String(c.ref.id)} onRow={(c) => setPicked(c.ref.id)} empty="no country recorded" />
              <p className="text-dim mt-2 text-2xs">each cell shows the latest value, the change since the first snapshot and its trend; click a row to chart it</p>
            </Section>
            {chosen && (
              <Section title={`${chosen.ref.label ?? chosen.ref.id} over game time`} scope={{ text: 'values at each shown snapshot', detail: 'click a point to open that snapshot' }}>
                <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
                  {METRICS.map((m) => {
                    const idx = chosen[m.key].map((v, i) => (v === null ? -1 : i)).filter((i) => i >= 0)
                    return (
                      <Card key={m.key} className="px-3 pt-2 pb-1">
                        <div className="flex justify-between text-xs">
                          <span className="font-medium">{m.label}</span>
                          <span className="num font-semibold">{compact(last(chosen[m.key]))}</span>
                        </div>
                        <LineChart
                          xs={idx.map((i) => d.hours[i])}
                          ys={idx.map((i) => chosen[m.key][i] as number)}
                          step
                          height={120}
                          xFormat={yearOf}
                          tip={(k) => `${yearOf(d.hours[idx[k]])} · snapshot ${n(d.seqs[idx[k]])}`}
                          onPick={(k) => navigate(`/runs/${run}/snapshots/${d.seqs[idx[k]]}`)}
                        />
                      </Card>
                    )
                  })}
                </div>
              </Section>
            )}
          </div>
        )
      }}
    </Loading>
  )
}
