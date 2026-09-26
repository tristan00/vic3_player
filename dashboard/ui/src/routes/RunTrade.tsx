import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LineChart } from '@/components/charts'
import { Card, ErrorState, Loading, RefLink, Section, Swatch } from '@/components/primitives'
import { yearOf } from '@/components/SeriesChart'
import { Table, type Col } from '@/components/Table'
import { qs, useApi, type S } from '@/lib/api'
import { cn, compact, label, n } from '@/lib/format'

type Goods = S['MarketGoods']

function GoodsHistory({ run, market, goods }: { run: number; market: number; goods: string }) {
  const navigate = useNavigate()
  const state = useApi<S['TradeSeries']>(`/api/runs/${run}/trade/goods${qs({ market, goods })}`)
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />
  if (!state.data) return <Card className="h-48 animate-pulse" />
  const d = state.data
  const chart = (title: string, values: (number | null)[]) => {
    const idx = values.map((v, i) => (v === null ? -1 : i)).filter((i) => i >= 0)
    return (
      <Card className="px-3 pt-2 pb-1">
        <div className="text-xs font-medium">{title}</div>
        <LineChart
          xs={idx.map((i) => d.hours[i])}
          ys={idx.map((i) => values[i] as number)}
          step
          height={120}
          xFormat={yearOf}
          tip={(k) => `${yearOf(d.hours[idx[k]])} · snapshot ${d.seqs[idx[k]]}`}
          onPick={(k) => navigate(`/runs/${run}/snapshots/${d.seqs[idx[k]]}`)}
        />
      </Card>
    )
  }
  return (
    <Section title={`${label(goods)} in this market`} scope={d.scope}>
      <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
        {chart('price', d.price)}
        {chart('supply (sell orders)', d.sell)}
        {chart('demand (buy orders)', d.buy)}
        <Card className="px-3 pt-2 pb-1">
          <div className="text-xs font-medium">world market price <span className="text-dim text-2xs">samples the game kept, in order</span></div>
          <LineChart xs={d.world_n} ys={d.world_price} height={120} xFormat={(x) => `#${n(x)}`} tip={(k) => `sample ${d.world_n[k]}`} empty="no world market samples" />
        </Card>
      </div>
    </Section>
  )
}

export function RunTrade({ run }: { run: number }) {
  const [market, setMarket] = useState<number | null>(null)
  const [seq, setSeq] = useState<string>('')
  const [goods, setGoods] = useState<string | null>(null)
  const state = useApi<S['TradePage']>(`/api/runs/${run}/trade${qs({ market, seq })}`)
  return (
    <Loading state={state} rows={12}>
      {(d) => {
        const cols: Col<Goods>[] = [
          { key: 'goods', label: 'goods', value: (g) => g.goods, render: (g) => <span className={cn('linka', goods === g.goods && 'font-semibold')}>{label(g.goods)}</span> },
          { key: 'price', label: 'price', align: 'right', value: (g) => g.price, render: (g) => compact(g.price) },
          { key: 'base', label: 'base cost', align: 'right', value: (g) => g.base, render: (g) => compact(g.base) },
          {
            key: 'ratio',
            label: 'price vs base',
            align: 'right',
            value: (g) => (g.base ? g.price / g.base : null),
            render: (g) => (g.base ? `${((100 * g.price) / g.base).toFixed(0)}%` : '—'),
          },
          { key: 'sell', label: 'supply', align: 'right', value: (g) => g.sell, render: (g) => compact(g.sell) },
          { key: 'buy', label: 'demand', align: 'right', value: (g) => g.buy, render: (g) => compact(g.buy) },
          {
            key: 'balance',
            label: 'supply − demand',
            align: 'right',
            value: (g) => g.sell - g.buy,
            render: (g) => (
              <span className="inline-flex items-center justify-end gap-1.5">
                <Swatch color={g.sell >= g.buy ? 'var(--done)' : 'var(--invalid)'} />
                {compact(g.sell - g.buy)}
              </span>
            ),
          },
        ]
        return (
          <div className="space-y-6">
            <Section title="markets" scope={d.scope} right={<span className="text-dim text-xs">{d.game_date.text}</span>}>
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                <select value={d.market ?? ''} onChange={(e) => { setMarket(Number(e.target.value)); setGoods(null) }} className="border-line rounded-md border px-2 py-1">
                  {d.markets.map((m) => (
                    <option key={m.market} value={m.market}>
                      market of {m.owner.label ?? m.owner.id} · {m.goods} goods{m.player ? ' · the player trades here' : ''}
                    </option>
                  ))}
                </select>
                <label className="flex items-center gap-1.5">
                  <span className="text-dim">as of snapshot</span>
                  <input type="number" min={0} key={d.seq} defaultValue={d.seq} onKeyDown={(e) => e.key === 'Enter' && setSeq((e.target as HTMLInputElement).value)}
                    onBlur={(e) => e.target.value !== String(d.seq) && setSeq(e.target.value)} className="border-line num w-24 rounded-md border px-2 py-1" />
                </label>
                {seq && <button className="linka" onClick={() => setSeq('')}>latest</button>}
                {d.markets.find((m) => m.market === d.market) && (
                  <span className="text-dim">
                    owned by <RefLink run={run} refd={d.markets.find((m) => m.market === d.market)!.owner} />
                  </span>
                )}
              </div>
              <Table rows={d.goods} cols={cols} rowKey={(g) => g.goods} onRow={(g) => setGoods(g.goods)} empty="this market trades nothing at this snapshot" />
              <p className="text-dim mt-2 text-2xs">click a goods row for its history in this market</p>
            </Section>
            {goods && d.market !== null && <GoodsHistory run={run} market={d.market} goods={goods} />}
          </div>
        )
      }}
    </Loading>
  )
}
