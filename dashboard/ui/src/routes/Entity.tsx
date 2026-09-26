import { ChevronDown, ChevronRight } from 'lucide-react'
import { Fragment, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ActionTable } from '@/components/ActionTable'
import { LineChart } from '@/components/charts'
import { Card, CellView, cellText, ErrorState, KV, Loading, Section } from '@/components/primitives'
import { SeriesView, yearOf } from '@/components/SeriesChart'
import { useApi, type Cell, type S } from '@/lib/api'
import { cn, compact, label, n } from '@/lib/format'

function same(a: Cell, b: Cell) {
  return cellText(a) === cellText(b)
}

function VersionTable({ run, table, versions }: { run: number; table: S['EntityTable']; versions: S['Version'][] }) {
  return (
    <div className="tablewrap max-h-[520px]">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-line border-b">
            <th className="text-dim px-3 py-1.5 text-right font-medium">snapshot</th>
            <th className="text-dim px-3 py-1.5 text-left font-medium">game date</th>
            {table.columns.map((c) => (
              <th key={c.name} className={cn('text-dim px-3 py-1.5 font-medium whitespace-nowrap', c.kind === 'number' ? 'text-right' : 'text-left')}>
                {label(c.name)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...versions].reverse().map((v, k, all) => {
            const prev = all[k + 1]
            return (
              <tr key={v.seq} className="border-line/60 border-b last:border-0">
                <td className="num px-3 py-1.5 text-right">
                  <Link className="linka" to={`/runs/${run}/snapshots/${v.seq}`}>
                    {v.seq}
                  </Link>
                </td>
                <td className="num text-dim px-3 py-1.5 whitespace-nowrap">{v.game_date.text}</td>
                {!v.present ? (
                  <td colSpan={table.columns.length} className="px-3 py-1.5">
                    <span className="bg-bad-soft rounded px-1.5 text-2xs">gone</span>
                  </td>
                ) : (
                  v.cells.map((c, i) => (
                    <td key={i} className={cn('px-3 py-1.5', table.columns[i].kind === 'number' ? 'text-right' : 'text-left', prev?.present && !same(c, prev.cells[i]) && 'bg-accent-soft')}>
                      <CellView run={run} cell={c} />
                    </td>
                  ))
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function NumericCharts({ run, table, versions }: { run: number; table: S['EntityTable']; versions: S['Version'][] }) {
  const navigate = useNavigate()
  const shown = versions.filter((v) => v.present)
  const charts = table.columns
    .map((c, i) => ({ c, i }))
    .filter(({ c, i }) => c.kind === 'number' && new Set(shown.map((v) => v.cells[i].num)).size > 1)
  if (!charts.length) return null
  return (
    <div className="grid gap-3 p-3 md:grid-cols-2 2xl:grid-cols-3">
      {charts.map(({ c, i }) => {
        const pts = shown.filter((v) => v.cells[i].num !== null && v.cells[i].num !== undefined)
        return (
          <Card key={c.name} className="px-3 pt-2 pb-1">
            <div className="flex justify-between text-xs">
              <span className="font-medium">{label(c.name)}</span>
              <span className="num font-semibold">{compact(pts[pts.length - 1]?.cells[i].num)}</span>
            </div>
            <LineChart
              xs={pts.map((v) => v.game_date.hours)}
              ys={pts.map((v) => v.cells[i].num as number)}
              step
              height={110}
              xFormat={yearOf}
              tip={(k) => `${pts[k].game_date.text} · snapshot ${pts[k].seq}`}
              onPick={(k) => navigate(`/runs/${run}/snapshots/${pts[k].seq}`)}
            />
          </Card>
        )
      })}
    </div>
  )
}

function KeyedTable({ run, table }: { run: number; table: S['EntityTable'] }) {
  const [open, setOpen] = useState<number | null>(null)
  if (!table.keys.length) {
    const versions = table.groups[0]?.versions ?? []
    return (
      <div>
        <NumericCharts run={run} table={table} versions={versions} />
        <VersionTable run={run} table={table} versions={versions} />
      </div>
    )
  }
  return (
    <div className="tablewrap max-h-[640px]">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-line border-b">
            <th className="w-6" />
            {table.keys.map((k) => (
              <th key={k.name} className="text-dim px-3 py-1.5 text-left font-medium">
                {label(k.name)}
              </th>
            ))}
            <th className="text-dim px-3 py-1.5 text-left font-medium">latest</th>
            {table.columns.map((c) => (
              <th key={c.name} className={cn('text-dim px-3 py-1.5 font-medium whitespace-nowrap', c.kind === 'number' ? 'text-right' : 'text-left')}>
                {label(c.name)}
              </th>
            ))}
            <th className="text-dim px-3 py-1.5 text-right font-medium">versions</th>
          </tr>
        </thead>
        <tbody>
          {table.groups.map((g, gi) => {
            const last = g.versions[g.versions.length - 1]
            return (
              <Fragment key={gi}>
                <tr className="border-line/60 hover:bg-raised cursor-pointer border-b" onClick={() => setOpen(open === gi ? null : gi)}>
                  <td className="pl-2">{open === gi ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}</td>
                  {g.keys.map((k, i) => (
                    <td key={i} className="px-3 py-1.5">
                      <CellView run={run} cell={k} />
                    </td>
                  ))}
                  <td className="px-3 py-1.5">{last.present ? <span className="num text-dim">{last.game_date.text}</span> : <span className="bg-bad-soft rounded px-1.5 text-2xs">gone {last.game_date.text}</span>}</td>
                  {table.columns.map((c, i) => (
                    <td key={c.name} className={cn('px-3 py-1.5', c.kind === 'number' ? 'text-right' : 'text-left')}>
                      {last.present ? <CellView run={run} cell={last.cells[i]} /> : null}
                    </td>
                  ))}
                  <td className="num px-3 py-1.5 text-right">{n(g.versions.length)}</td>
                </tr>
                {open === gi && (
                  <tr>
                    <td colSpan={table.keys.length + table.columns.length + 3} className="bg-bg">
                      <NumericCharts run={run} table={table} versions={g.versions} />
                      <VersionTable run={run} table={table} versions={g.versions} />
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function LazyTable({ run, kind, id, t }: { run: number; kind: string; id: number; t: S['TableCount'] }) {
  const [open, setOpen] = useState(false)
  const state = useApi<S['EntityTable']>(open ? `/api/runs/${run}/entities/${kind}/${id}/tables/${t.table}` : null)
  return (
    <div>
      <button className="hover:bg-raised flex w-full items-center gap-2 px-3 py-2 text-left text-xs" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        <code className="font-medium">{t.table}</code>
        <span className="text-dim text-2xs">{t.kind}</span>
        <span className="num ml-auto">{n(t.rows)} rows</span>
      </button>
      {open && (
        <div className="border-line border-t">
          {state.error ? <ErrorState error={state.error} onRetry={state.reload} /> : state.data ? <KeyedTable run={run} table={state.data} /> : <div className="text-dim px-3 py-3 text-2xs">loading…</div>}
        </div>
      )}
    </div>
  )
}

export function Entity() {
  const params = useParams()
  const run = Number(params.run)
  const kind = params.kind!
  const id = Number(params.id)
  const state = useApi<S['EntityDetail']>(`/api/runs/${run}/entities/${kind}/${id}`)
  return (
    <Loading state={state} rows={12}>
      {(d) => {
        const versions = d.history?.groups[0]?.versions ?? []
        const last = versions[versions.length - 1]
        const others = d.tables.filter((t) => t.table !== `${kind}_history`)
        return (
          <div className="space-y-8">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <Link className="linka text-sm" to={`/runs/${run}/entities/${kind}`}>
                run {run} · {label(kind)}
              </Link>
              <h1 className="text-xl font-semibold tracking-tight">{d.ref.label ?? `${label(kind)} ${id}`}</h1>
              <span className="text-dim num text-xs">id {id}</span>
              {d.present ? <span className="bg-ok-soft rounded-full px-2 py-0.5 text-2xs">present</span> : <span className="bg-bad-soft rounded-full px-2 py-0.5 text-2xs">not present at the last version</span>}
              <span className="text-dim text-xs">
                first seen at{' '}
                <Link className="linka" to={`/runs/${run}/snapshots/${d.first_seq}`}>
                  snapshot {d.first_seq}
                </Link>
              </span>
            </div>
            <p className="text-dim text-2xs">
              {d.scope.text} · {d.scope.detail}
            </p>

            {d.history && last?.present && (
              <Section title="latest values" scope={{ text: `${label(kind)}_history at snapshot ${last.seq}`, detail: last.game_date.text }}>
                <Card className="px-4 py-3">
                  <div className="grid gap-x-10 gap-y-1 md:grid-cols-2 xl:grid-cols-3">
                    {d.history.columns.map((c, i) => (
                      <KV key={c.name} items={[[label(c.name), <CellView key={c.name} run={run} cell={last.cells[i]} />]]} />
                    ))}
                  </div>
                </Card>
              </Section>
            )}

            {d.history && (
              <Section title="history" scope={{ text: `every version of ${label(kind)}_history for this ${label(kind)}, newest first`, detail: 'shaded cells changed from the version below' }}>
                <Card className="overflow-hidden">
                  <KeyedTable run={run} table={d.history} />
                </Card>
              </Section>
            )}
            {!d.history && <Card className="text-dim px-4 py-4 text-xs">the recorder never captured this {label(kind)} itself; other tables only refer to it</Card>}

            {d.series.length > 0 && (
              <Section title="trends the game kept" scope={{ text: `sample buffers owned by this ${label(kind)}`, detail: 'in sample order; the game dates only some samples' }}>
                <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
                  {d.series.map((s) => (
                    <SeriesView key={s.label} run={run} series={s} />
                  ))}
                </div>
              </Section>
            )}

            {others.length > 0 && (
              <Section title="more about it" scope={{ text: `other tables the recorder keeps per ${label(kind)}`, detail: 'open one to load its versions' }}>
                <Card className="divide-line divide-y overflow-hidden">
                  {others.map((t) => (
                    <LazyTable key={t.table} run={run} kind={kind} id={id} t={t} />
                  ))}
                </Card>
              </Section>
            )}

            <Section title="actions that named it" scope={{ text: `actions of run ${run} with this ${label(kind)} as a parameter, newest first`, detail: 'up to 200' }}>
              <ActionTable rows={d.actions} empty={`no action named this ${label(kind)}`} />
            </Section>
          </div>
        )
      }}
    </Loading>
  )
}
