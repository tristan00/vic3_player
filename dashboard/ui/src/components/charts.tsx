import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { cn, compact, num } from '@/lib/format'

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}

function niceTicks(lo: number, hi: number, count = 4): number[] {
  if (lo === hi) return [lo]
  const raw = (hi - lo) / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toPrecision(12))
  return out
}

function thin(xs: number[], ys: number[], buckets: number): number[] {
  if (xs.length <= buckets * 2) return xs.map((_, i) => i)
  const keep = new Set<number>([0, xs.length - 1])
  const per = xs.length / buckets
  for (let b = 0; b < buckets; b++) {
    const from = Math.floor(b * per)
    const to = Math.min(xs.length, Math.floor((b + 1) * per))
    let lo = from
    let hi = from
    for (let i = from; i < to; i++) {
      if (ys[i] < ys[lo]) lo = i
      if (ys[i] > ys[hi]) hi = i
    }
    keep.add(lo)
    keep.add(hi)
  }
  return [...keep].sort((a, b) => a - b)
}

export function LineChart({
  xs,
  ys,
  step = false,
  height = 150,
  xFormat,
  yFormat = compact,
  tip,
  onPick,
  empty = '0 values',
}: {
  xs: number[]
  ys: number[]
  step?: boolean
  height?: number
  xFormat: (x: number) => string
  yFormat?: (y: number) => string
  tip?: (i: number) => ReactNode
  onPick?: (i: number) => void
  empty?: string
}) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const pad = { l: 48, r: 12, t: 10, b: 22 }
  const w = Math.max(0, width - pad.l - pad.r)
  const h = height - pad.t - pad.b
  const geo = useMemo(() => {
    if (!xs.length) return null
    const x0 = Math.min(...xs)
    const x1 = Math.max(...xs)
    let y0 = Math.min(...ys)
    let y1 = Math.max(...ys)
    if (y0 === y1) {
      y0 -= Math.abs(y0) * 0.1 || 1
      y1 += Math.abs(y1) * 0.1 || 1
    }
    const yt = niceTicks(y0, y1)
    y0 = Math.min(y0, yt[0])
    y1 = Math.max(y1, yt[yt.length - 1])
    const sx = (x: number) => (x1 === x0 ? w / 2 : ((x - x0) / (x1 - x0)) * w)
    const sy = (y: number) => h - ((y - y0) / (y1 - y0)) * h
    const idx = thin(xs, ys, Math.max(1, Math.floor(w)))
    let d = ''
    idx.forEach((i, k) => {
      const X = sx(xs[i])
      const Y = sy(ys[i])
      if (k === 0) d += `M${X},${Y}`
      else d += step ? `H${X}V${Y}` : `L${X},${Y}`
    })
    if (step && idx.length) d += `H${w}`
    const xt = niceTicks(x0, x1, Math.max(2, Math.floor(w / 110)))
    return { sx, sy, d, yt, xt, x0, x1 }
  }, [xs, ys, w, h, step])

  if (!xs.length) return <div className="text-dim py-6 text-center text-2xs">{empty}</div>

  const nearest = (px: number) => {
    if (!geo) return null
    let best = 0
    let dist = Infinity
    for (let i = 0; i < xs.length; i++) {
      const d = Math.abs(geo.sx(xs[i]) - px)
      if (step ? geo.sx(xs[i]) <= px + 0.5 && d < dist : d < dist) {
        best = i
        dist = d
      }
    }
    return best
  }

  return (
    <div ref={ref} className="relative w-full select-none">
      {width > 0 && geo && (
        <svg
          width={width}
          height={height}
          role="img"
          onPointerMove={(e) => {
            const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect()
            setHover(nearest(e.clientX - r.left - pad.l))
          }}
          onPointerLeave={() => setHover(null)}
          onClick={() => hover !== null && onPick?.(hover)}
          className={cn(onPick && 'cursor-pointer')}
        >
          <g transform={`translate(${pad.l},${pad.t})`}>
            {geo.yt.map((t) => (
              <g key={t}>
                <line x1={0} x2={w} y1={geo.sy(t)} y2={geo.sy(t)} stroke="var(--grid)" strokeWidth={1} />
                <text x={-8} y={geo.sy(t)} dy="0.32em" textAnchor="end" fontSize={10} fill="var(--muted)" className="num">
                  {yFormat(t)}
                </text>
              </g>
            ))}
            {geo.xt.map((t) => (
              <text key={t} x={geo.sx(t)} y={h + 15} textAnchor="middle" fontSize={10} fill="var(--muted)" className="num">
                {xFormat(t)}
              </text>
            ))}
            <path d={geo.d} fill="none" stroke="var(--series)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {hover !== null && (
              <g>
                <line x1={geo.sx(xs[hover])} x2={geo.sx(xs[hover])} y1={0} y2={h} stroke="var(--muted)" strokeWidth={1} />
                <circle cx={geo.sx(xs[hover])} cy={geo.sy(ys[hover])} r={4} fill="var(--series)" stroke="var(--surface)" strokeWidth={2} />
              </g>
            )}
          </g>
        </svg>
      )}
      {hover !== null && geo && (
        <div
          className="bg-surface border-line pointer-events-none absolute top-1 z-10 rounded-md border px-2 py-1 text-2xs shadow-md"
          style={{ left: Math.min(width - 170, Math.max(0, pad.l + geo.sx(xs[hover]) + 10)) }}
        >
          <div className="num text-xs font-semibold">{num(ys[hover])}</div>
          <div className="text-dim">{tip ? tip(hover) : xFormat(xs[hover])}</div>
        </div>
      )}
    </div>
  )
}
