import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Card, CellView, CountText, Loading, Pager, RefLink, Section } from '@/components/primitives'
import { Table, type Col } from '@/components/Table'
import { qs, useApi, type S } from '@/lib/api'
import { label } from '@/lib/format'

const LIMIT = 100

export function Entities() {
  const params = useParams()
  const run = Number(params.run)
  const kind = params.kind!
  const navigate = useNavigate()
  const [search, setSearch] = useSearchParams()
  const offset = Number(search.get('offset') ?? 0)
  const seq = search.get('seq') ?? ''
  const gone = search.get('gone') === '1'
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(search)
    v ? next.set(k, v) : next.delete(k)
    if (k !== 'offset') next.delete('offset')
    setSearch(next, { replace: true })
  }
  const state = useApi<S['EntityList']>(`/api/runs/${run}/entities/${kind}${qs({ seq, offset, limit: LIMIT, gone: gone || null })}`)
  return (
    <Loading state={state} rows={14}>
      {(d) => {
        const cols: Col<S['EntityRow']>[] = [
          { key: 'ref', label: label(kind), value: (r) => r.ref.label ?? r.ref.id, render: (r) => <RefLink run={run} refd={r.ref} /> },
          { key: 'id', label: 'id', align: 'right', value: (r) => r.ref.id, render: (r) => <span className="text-dim">{r.ref.id}</span> },
          ...(gone ? [{ key: 'present', label: 'present', value: (r: S['EntityRow']) => (r.present ? 1 : 0), render: (r: S['EntityRow']) => (r.present ? 'yes' : <span className="bg-bad-soft rounded px-1.5 text-2xs">gone</span>) }] : []),
          {
            key: 'first',
            label: 'first seen',
            align: 'right',
            value: (r) => r.first_seq,
            render: (r) => (
              <Link className="linka" to={`/runs/${run}/snapshots/${r.first_seq}`} onClick={(e) => e.stopPropagation()}>
                #{r.first_seq}
              </Link>
            ),
          },
          ...d.columns.map((c, i) => ({
            key: c.name,
            label: label(c.name),
            align: c.kind === 'number' ? ('right' as const) : ('left' as const),
            value: (r: S['EntityRow']) => r.cells[i].num ?? r.cells[i].text ?? r.cells[i].ref?.label ?? null,
            render: (r: S['EntityRow']) => <CellView run={run} cell={r.cells[i]} />,
          })),
        ]
        return (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <Link className="linka text-sm" to={`/runs/${run}?view=entities`}>
                run {run}
              </Link>
              <h1 className="text-xl font-semibold tracking-tight">{label(kind)}</h1>
              <span className="text-dim text-xs">
                at snapshot <span className="num">{d.seq}</span> · {d.game_date.text}
              </span>
            </div>
            <Section title={`every ${label(kind)}`} scope={d.scope}>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Card className="px-3 py-1.5">
                  <CountText count={d.total} />
                </Card>
                <label className="flex items-center gap-1.5 text-xs">
                  <span className="text-dim">as of snapshot</span>
                  <input
                    type="number"
                    min={0}
                    defaultValue={seq || d.seq}
                    key={d.seq}
                    onKeyDown={(e) => e.key === 'Enter' && set('seq', (e.target as HTMLInputElement).value)}
                    onBlur={(e) => e.target.value !== String(d.seq) && set('seq', e.target.value)}
                    className="border-line num w-24 rounded-md border px-2 py-1"
                  />
                </label>
                {seq && (
                  <button className="linka text-xs" onClick={() => set('seq', '')}>
                    latest
                  </button>
                )}
                <label className="flex items-center gap-1.5 text-xs">
                  <input type="checkbox" checked={gone} onChange={(e) => set('gone', e.target.checked ? '1' : '')} />
                  include gone
                </label>
                <div className="ml-auto">
                  <Pager offset={offset} limit={LIMIT} shown={d.rows.length} total={d.total.value} onOffset={(o) => set('offset', String(o))} />
                </div>
              </div>
              <Table rows={d.rows} cols={cols} rowKey={(r) => String(r.ref.id)} onRow={(r) => navigate(`/runs/${run}/entities/${kind}/${r.ref.id}`)} empty={`no ${label(kind)} at this snapshot`} why="try an earlier snapshot, or include gone ones" />
              <p className="text-dim mt-2 text-2xs">sorting applies to this page of rows</p>
            </Section>
          </div>
        )
      }}
    </Loading>
  )
}
