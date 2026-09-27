import { useParams } from 'react-router-dom'
import { DataGrid } from '@/components/DataGrid'
import { Card, Loading, Section } from '@/components/primitives'
import { useApi, type S } from '@/lib/api'
import { num } from '@/lib/format'
import { ScopeInput, useScope } from '@/routes/Actions'

export function ActionType() {
  const name = useParams().name!
  const { scope } = useScope()
  const info = useApi<S['ActionInfo']>(`/api/actions/${name}`)
  const base = `/api/actions/${name}`
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <h1 className="num font-semibold">{name}</h1>
        <ScopeInput />
      </div>
      <Loading state={info}>
        {(d) => (
          <Card className="inline-block overflow-hidden">
            <table className="text-xs">
              <tbody>
                <tr className="border-line/60 border-b">
                  <td className="text-dim px-2 py-0.5">group</td>
                  <td className="px-2 py-0.5">{d.group}</td>
                </tr>
                <tr className="border-line/60 border-b">
                  <td className="text-dim px-2 py-0.5">default weight</td>
                  <td className="num px-2 py-0.5">{num(d.weight)}</td>
                </tr>
                {d.params.map((p) => (
                  <tr key={p.name} className="border-line/60 border-b last:border-0">
                    <td className="text-dim px-2 py-0.5">param {p.name}</td>
                    <td className="px-2 py-0.5">{p.kind}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </Loading>
      <Section title="by status and detail">
        <DataGrid id="details" url={`${base}/details`} query={{ scope }} />
      </Section>
      <Section title="by run">
        <DataGrid id="runs" url={`${base}/runs`} query={{ scope }} />
      </Section>
      <Section title="loop_action">
        <DataGrid id="picks" url={`${base}/picks`} query={{ scope }} />
      </Section>
    </div>
  )
}
