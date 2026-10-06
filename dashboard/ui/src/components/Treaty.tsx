import { Link } from 'react-router-dom'
import { Section } from '@/components/primitives'
import type { Ref, S } from '@/lib/api'
import { label, n } from '@/lib/format'

function Party({ value, seq }: { value: Ref | null; seq: number }) {
  return value ? <Link className="linka" to={`/runs/${value.run}/entities/country/${value.id}?seq=${seq}`}>{value.label ?? value.id}</Link> : <span className="text-dim">—</span>
}

export function Treaty({ treaty, seq }: { treaty: S['TreatyInfo'] | null | undefined; seq: string }) {
  if (!treaty) return <p className="text-dim">Treaty not yet recorded at this snapshot.</p>
  const days = treaty.binding_period_days
  const duration = days % 365 === 0 ? `${n(days / 365)} ${days === 365 ? 'year' : 'years'}` : `${n(days)} days`
  const selected = seq ? Number(seq) : treaty.seq
  return <Section title="Treaty terms">
    <div className="border-line overflow-hidden rounded border">
      <div className="bg-raised flex flex-wrap items-center gap-x-6 gap-y-2 px-3 py-2 text-sm">
        <span className="font-semibold"><Party value={treaty.first} seq={selected} /> <span className="text-dim">and</span> <Party value={treaty.second} seq={selected} /></span>
        <span className="font-medium">{treaty.status}</span>
        {treaty.entered_into_force_on && <span><span className="text-dim">In force since </span>{treaty.entered_into_force_on.text}</span>}
        <span><span className="text-dim">Binding period </span>{duration}</span>
        {treaty.binding_until && <span><span className="text-dim">Binding until </span>{treaty.binding_until.text}</span>}
      </div>
      {treaty.status === 'No longer present' && <div className="text-dim px-3 py-2 text-xs">Last terms before removal · <Link className="linka" to={`/runs/${treaty.first.run}/snapshots/${treaty.seq}`}>snapshot {treaty.seq}</Link></div>}
      {treaty.terms.length ? <table className="w-full text-left text-sm">
        <thead className="text-dim border-line border-y text-xs"><tr><th className="px-3 py-2 font-medium">Article</th><th className="px-3 py-2 font-medium">From</th><th className="px-3 py-2 font-medium">To</th></tr></thead>
        <tbody>{treaty.terms.map((term) => <tr key={term.article.id} className="border-line border-b last:border-0">
          <td className="px-3 py-2"><Link className="linka capitalize" to={`/runs/${term.article.run}/entities/treaty_article/${term.article.id}?seq=${treaty.seq}`}>{label(term.article.label ?? String(term.article.id))}</Link></td>
          <td className="px-3 py-2"><Party value={term.source} seq={treaty.seq} /></td>
          <td className="px-3 py-2"><Party value={term.target} seq={treaty.seq} /></td>
        </tr>)}</tbody>
      </table> : <p className="text-dim px-3 py-2 text-sm">No articles recorded at this snapshot.</p>}
    </div>
  </Section>
}
