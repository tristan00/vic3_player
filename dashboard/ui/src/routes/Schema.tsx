import { DataGrid } from '@/components/DataGrid'
import { Section } from '@/components/primitives'

export function Schema() {
  return (
    <div className="space-y-5">
      <Section title="recorded columns">
        <DataGrid id="schema" url="/api/schema" limit={500} />
      </Section>
      <Section title="capture_gap">
        <DataGrid id="gaps" url="/api/meta/capture_gap" limit={500} />
      </Section>
    </div>
  )
}
