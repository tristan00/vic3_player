import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { fraction, gameDate, label, num, short, sum } from './format'

const LEFT = 48
const RIGHT = 14
const TOP = 8
const BOTTOM = 22

export function useWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    setWidth(element.clientWidth)
    const observer = new ResizeObserver(() => setWidth(element.clientWidth))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return [ref, width]
}

const ROW = 22
const WORD = 40
const DIGITS = [1, 2, 5]

function ticks(low: number, high: number, pixels: number): number[] {
  const apart = Math.max(ROW, Math.min(0.3 * pixels - 20, WORD + pixels / 24))
  const least = ((high - low) * apart) / pixels
  const multiple = (rung: number, count: number) => Number(`${count * DIGITS[rung - 3 * Math.floor(rung / 3)]}e${Math.floor(rung / 3)}`)
  const marks = (rung: number) => {
    const step = multiple(rung, 1)
    const found: number[] = []
    for (let index = Math.ceil(low / step - 1e-9); index <= Math.floor(high / step + 1e-9); index += 1) {
      const value = multiple(rung, index)
      if (value >= low && value <= high) found.push(value)
    }
    return found
  }
  let rung = 3 * (Math.floor(Math.log10(least)) - 1)
  while (multiple(rung, 1) < least) rung += 1
  let found = marks(rung)
  for (let finer = 0; found.length < 2 && finer < 6; finer += 1) found = marks((rung -= 1))
  return found
}

function extent(values: number[], zero: boolean): [number, number] {
  let low = Math.min(...values)
  let high = Math.max(...values)
  if (zero) {
    low = Math.min(low, 0)
    high = Math.max(high, 0)
  }
  if (low === high) {
    const pad = zero ? Math.abs(low) * 0.1 || 1 : 1
    return [low - pad, high + pad]
  }
  const pad = (high - low) * 0.06
  return [zero && low === 0 ? 0 : low - pad, zero && high === 0 ? 0 : high + pad]
}

function plain(value: number) {
  return String(Number(value.toFixed(2)))
}

function Frame({ width, height, xs, ys, px, py, x, y, children }: { width: number; height: number; xs: number[]; ys: number[]; px: (v: number) => number; py: (v: number) => number; x: (v: number) => string; y: (v: number) => string; children: ReactNode }) {
  return (
    <>
      {ys.map((value) => (
        <g key={`y${value}`}>
          <line x1={LEFT} x2={width - RIGHT} y1={py(value)} y2={py(value)} className={value === 0 ? 'rule zero' : 'rule'} />
          <text x={LEFT - 6} y={py(value)} dy="0.32em" textAnchor="end" className="tick">
            {y(value)}
          </text>
        </g>
      ))}
      {xs.map((value) => (
        <text key={`x${value}`} x={px(value)} y={height - 6} textAnchor="middle" className="tick">
          {x(value)}
        </text>
      ))}
      {children}
    </>
  )
}

function Tip({ at, width, children }: { at: number; width: number; children: ReactNode }) {
  const right = at > width * 0.6
  return (
    <div className="tip" style={right ? { right: width - at + 10 } : { left: at + 10 }}>
      {children}
    </div>
  )
}

export function Legend({ palette, keys }: { palette: Record<string, string>; keys: string[] }) {
  return (
    <div className="legend">
      {keys.map((key) => (
        <span key={key}>
          <i style={{ background: palette[key] }} />
          {label(key)}
        </span>
      ))}
    </div>
  )
}

function stretches(points: [number, number | null][], step: boolean): [number, number][][] {
  const out: [number, number][][] = []
  let current: [number, number][] = []
  let last: number | null = null
  for (const [at, value] of points) {
    const missing = value === null || !Number.isFinite(value)
    if (step && last !== null) current.push([at, last])
    if (missing) {
      if (current.length) out.push(current)
      current = []
      last = null
    } else {
      current.push([at, value])
      last = value
    }
  }
  if (current.length) out.push(current)
  return out
}

export type Series = { name: string; color: string; points: [number, number | null][]; heavy?: boolean }

export function Lines({ series, height = 190, x = plain, y = short, zero = false, title, at = gameDate, step = false }: { series: Series[]; height?: number; x?: (v: number) => string; y?: (v: number) => string; zero?: boolean; title?: string; at?: (v: number) => string; step?: boolean }) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  const drawn = series.map((line) => ({ ...line, points: line.points.filter((point) => point[1] !== null && Number.isFinite(point[1])) as [number, number][] })).filter((line) => line.points.length)
  const all = drawn.flatMap((line) => line.points)
  if (!all.length)
    return (
      <div ref={ref} className="chart">
        {title && <div className="chart-title">{title}</div>}
        <div className="none" style={{ height: height - 20 }}>
          no values
        </div>
      </div>
    )
  if (drawn.every((line) => line.points.length < 2))
    return (
      <div ref={ref} className="chart">
        {title && <div className="chart-title">{title}</div>}
        <dl className="facts single">
          {drawn.map((line) => (
            <div key={line.name}>
              <dt>
                {label(line.name)} at {at(line.points[0][0])}
              </dt>
              <dd>{num(line.points[0][1])}</dd>
            </div>
          ))}
        </dl>
      </div>
    )
  const [x0, x1] = extent(all.map((point) => point[0]), false)
  const [y0, y1] = extent(all.map((point) => point[1]), zero)
  const px = (value: number) => LEFT + ((value - x0) / (x1 - x0)) * (width - LEFT - RIGHT)
  const py = (value: number) => TOP + (1 - (value - y0) / (y1 - y0)) * (height - TOP - BOTTOM)
  const nearest = (line: { points: [number, number][] }, at: number) => line.points.reduce((best, point) => (Math.abs(point[0] - at) < Math.abs(best[0] - at) ? point : best))
  const move = (event: React.MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const at = x0 + ((event.clientX - box.left - LEFT) / (width - LEFT - RIGHT)) * (x1 - x0)
    setHover(nearest({ points: all }, at)[0])
  }
  return (
    <div ref={ref} className="chart">
      {title && <div className="chart-title">{title}</div>}
      {drawn.length > 1 && <Legend palette={Object.fromEntries(drawn.map((line) => [line.name, line.color]))} keys={drawn.map((line) => line.name)} />}
      {width > 0 && (
        <svg width={width} height={height} onMouseMove={move} onMouseLeave={() => setHover(null)}>
          <Frame width={width} height={height} xs={ticks(x0, x1, width - LEFT - RIGHT)} ys={ticks(y0, y1, height - TOP - BOTTOM)} px={px} py={py} x={x} y={y}>
            {series.map((line) =>
              stretches(line.points, step).map((stretch, index) => (
                <polyline key={`${line.name} ${index}`} fill="none" stroke={line.color} strokeWidth={line.heavy ? 2.4 : 1.6} strokeLinejoin="round" points={stretch.map((point) => `${px(point[0]).toFixed(1)},${py(point[1]).toFixed(1)}`).join(' ')} />
              )),
            )}
            {drawn.map((line) => line.points.length === 1 && <circle key={line.name} cx={px(line.points[0][0])} cy={py(line.points[0][1])} r={3} fill={line.color} />)}
            {hover !== null && <line x1={px(hover)} x2={px(hover)} y1={TOP} y2={height - BOTTOM} className="cross" />}
            {hover !== null && drawn.map((line) => <circle key={line.name} cx={px(hover)} cy={py(nearest(line, hover)[1])} r={3.5} fill={line.color} stroke="#fff" strokeWidth={1.5} />)}
          </Frame>
        </svg>
      )}
      {hover !== null && (
        <Tip at={px(hover)} width={width}>
          <b>{at(hover)}</b>
          {drawn.map((line) => (
            <div key={line.name}>
              <i style={{ background: line.color }} />
              {label(line.name)} <b>{num(nearest(line, hover)[1])}</b>
            </div>
          ))}
        </Tip>
      )}
    </div>
  )
}

export type Column = { label: string; values: Record<string, number>; title?: string }

export function Columns({ data, keys, palette, height = 170, y = short, legend = true }: { data: Column[]; keys: string[]; palette: Record<string, string>; height?: number; y?: (v: number) => string; legend?: boolean }) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  if (!data.length)
    return (
      <div ref={ref} className="chart">
        <div className="none" style={{ height }}>
          none
        </div>
      </div>
    )
  const totals = data.map((column) => keys.reduce((total, key) => total + (column.values[key] || 0), 0))
  const [, y1] = extent([0, ...totals], true)
  const band = (width - LEFT - RIGHT) / data.length
  const bar = Math.max(1, Math.min(band - 2, 26))
  const py = (value: number) => TOP + (1 - value / y1) * (height - TOP - BOTTOM)
  const every = Math.max(1, Math.ceil(data.length / Math.max(2, Math.floor(width / 70))))
  return (
    <div ref={ref} className="chart">
      {legend && keys.length > 1 && <Legend palette={palette} keys={keys} />}
      {width > 0 && (
        <svg width={width} height={height} onMouseLeave={() => setHover(null)}>
          <Frame width={width} height={height} xs={[]} ys={ticks(0, y1, height - TOP - BOTTOM)} px={() => 0} py={py} x={plain} y={y}>
            {data.map((column, index) => {
              let base = 0
              const left = LEFT + band * index + (band - bar) / 2
              return (
                <g key={index} onMouseEnter={() => setHover(index)}>
                  <rect x={LEFT + band * index} y={TOP} width={band} height={height - TOP - BOTTOM} fill={hover === index ? '#0000000a' : 'transparent'} />
                  {keys.map((key) => {
                    const value = column.values[key] || 0
                    if (!value) return null
                    const top = py(base + value)
                    const size = py(base) - top
                    base += value
                    return <rect key={key} x={left} y={top} width={bar} height={Math.max(size - 1, 1)} fill={palette[key]} rx={1.5} />
                  })}
                  {index % every === 0 && (
                    <text x={LEFT + band * (index + 0.5)} y={height - 6} textAnchor="middle" className="tick">
                      {column.label}
                    </text>
                  )}
                </g>
              )
            })}
          </Frame>
        </svg>
      )}
      {hover !== null && data[hover] && (
        <Tip at={LEFT + band * (hover + 0.5)} width={width}>
          <b>{data[hover].title ?? data[hover].label}</b>
          {keys
            .filter((key) => data[hover].values[key])
            .map((key) => (
              <div key={key}>
                <i style={{ background: palette[key] }} />
                {label(key)} <b>{num(data[hover].values[key])}</b>
              </div>
            ))}
        </Tip>
      )}
    </div>
  )
}

export type Dot = { x: number; y: number; key: string; title: string; to?: string }

function regression(points: Dot[]) {
  const mx = sum(points.map((point) => point.x)) / points.length
  const my = sum(points.map((point) => point.y)) / points.length
  const xx = sum(points.map((point) => (point.x - mx) ** 2))
  const xy = sum(points.map((point) => (point.x - mx) * (point.y - my)))
  const yy = sum(points.map((point) => (point.y - my) ** 2))
  return { r: xy / Math.sqrt(xx * yy), at: (value: number) => my + (xy / xx) * (value - mx) }
}

export function Dots({ points, palette, height = 190, x = plain, y = short, line, fit = false, zero = true, legend = true, xTitle, yTitle, clip }: { points: Dot[]; palette: Record<string, string>; height?: number; x?: (v: number) => string; y?: (v: number) => string; line?: [number, number][]; fit?: boolean; zero?: boolean; legend?: boolean; xTitle?: string; yTitle?: string; clip?: [number, number] }) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState<Dot | null>(null)
  const navigate = useNavigate()
  const kept = points.filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y))
  if (!kept.length)
    return (
      <div ref={ref} className="chart">
        <div className="none" style={{ height }}>
          none
        </div>
      </div>
    )
  const ordered = kept.map((point) => point.y).sort((a, b) => a - b)
  const inside = clip ? ordered.slice(Math.floor(clip[0] * (ordered.length - 1)), Math.ceil(clip[1] * (ordered.length - 1)) + 1) : ordered
  const [x0, x1] = extent(kept.map((point) => point.x), false)
  const straight = fit ? regression(kept) : null
  const ends = straight && Number.isFinite(straight.r) ?[Math.min(...kept.map((point) => point.x)), Math.max(...kept.map((point) => point.x))].map((at) => [at, straight.at(at)]) : []
  const [y0, y1] = extent([...inside, ...ends.map((end) => end[1])], zero)
  const beyond = kept.filter((point) => point.y < y0 || point.y > y1).length
  const px = (value: number) => LEFT + ((value - x0) / (x1 - x0)) * (width - LEFT - RIGHT)
  const py = (value: number) => TOP + (1 - (Math.max(y0, Math.min(y1, value)) - y0) / (y1 - y0)) * (height - TOP - BOTTOM)
  const keys = [...new Set(kept.map((point) => point.key))].sort()
  const find = (event: React.MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const mx = event.clientX - box.left
    const my = event.clientY - box.top
    let best: Dot | null = null
    let reach = 18 ** 2
    for (const point of kept) {
      const distance = (px(point.x) - mx) ** 2 + (py(point.y) - my) ** 2
      if (distance < reach) {
        reach = distance
        best = point
      }
    }
    return best
  }
  return (
    <div ref={ref} className="chart">
      {legend && keys.length > 1 && <Legend palette={palette} keys={keys} />}
      {width > 0 && (
        <svg width={width} height={height} onMouseMove={(event) => setHover(find(event))} onMouseLeave={() => setHover(null)} onClick={(event) => {
          const picked = find(event)
          if (picked?.to) navigate(picked.to)
        }} style={{ cursor: hover?.to ? 'pointer' : 'default' }}>
          <Frame width={width} height={height} xs={ticks(x0, x1, width - LEFT - RIGHT)} ys={ticks(y0, y1, height - TOP - BOTTOM)} px={px} py={py} x={x} y={y}>
            {line && line.length > 1 && <polyline fill="none" className="trend" points={line.map((point) => `${px(point[0]).toFixed(1)},${py(point[1]).toFixed(1)}`).join(' ')} />}
            {kept.map((point, index) =>
              point.y < y0 || point.y > y1 ? (
                <circle key={index} cx={px(point.x)} cy={py(point.y)} r={hover === point ? 5 : 3.2} fill="#fff" stroke={palette[point.key]} strokeWidth={1.6} />
              ) : (
                <circle key={index} cx={px(point.x)} cy={py(point.y)} r={hover === point ? 5 : 3.2} fill={palette[point.key]} stroke="#fff" strokeWidth={1} />
              ),
            )}
            {straight && ends.length > 0 && (
              <>
                <line className="fit" x1={px(ends[0][0])} y1={py(ends[0][1])} x2={px(ends[1][0])} y2={py(ends[1][1])} />
                <text className="fit-label" x={px(ends[1][0])} y={py(ends[1][1]) < TOP + 18 ? py(ends[1][1]) + 16 : py(ends[1][1]) - 8} textAnchor="end">
                  r = {straight.r.toFixed(2)}
                </text>
              </>
            )}
          </Frame>
        </svg>
      )}
      {(xTitle || yTitle) && (
        <div className="axes">
          {yTitle} by {xTitle}
          {beyond > 0 ? ` · ${beyond} clipped` : ''}
        </div>
      )}
      {hover && (
        <Tip at={px(hover.x)} width={width}>
          <b>{hover.title}</b>
          <div>
            <i style={{ background: palette[hover.key] }} />
            {label(hover.key)} <b>{num(hover.y)}</b>
          </div>
        </Tip>
      )}
    </div>
  )
}

export function Multiples({ x, axis, values, columns }: { x: number[]; axis: string; values: Record<string, (number | null)[]>; columns: string[] }) {
  const steady = columns.filter((column) => new Set(values[column]).size <= 1)
  const moving = columns.filter((column) => !steady.includes(column))
  return (
    <>
      <div className="multiples">
        {moving.map((column) => (
          <Lines key={column} title={label(column)} height={120} step={axis === 'year'} at={axis === 'year' ? gameDate : (value) => `${label(axis)} ${value}`} series={[{ name: column, color: '#2a78d6', points: x.map((at, index) => [at, values[column][index]]) }]} />
        ))}
      </div>
      {steady.length > 0 && (
        <dl className="facts steady">
          {steady.map((column) => (
            <div key={column}>
              <dt>{label(column)}</dt>
              <dd>{num(values[column].find((value) => value !== null) ?? null) || 'none'}</dd>
            </div>
          ))}
        </dl>
      )}
    </>
  )
}

export function Share({ value, color = '#2a78d6' }: { value: number | null; color?: string }) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null
  return (
    <span className="share">
      <span className="share-number">{fraction(value)}</span>
      <span className="share-track">
        <span style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, background: color }} />
      </span>
    </span>
  )
}
