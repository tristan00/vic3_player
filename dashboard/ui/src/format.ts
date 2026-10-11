export const PALETTE = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']

export function phaseTone(phase: string) {
  return phase === 'running' || phase === 'starting' ? 'live' : phase === 'failed' || phase === 'lost' ? 'bad' : 'plain'
}

export function label(name: string) {
  return name.replace(/_/g, ' ')
}

export function heading(name: string) {
  return name.length <= 3 ? name.toUpperCase() : label(name).replace(/^./, (first) => first.toUpperCase())
}

export function num(value: any, digits = 4): string {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value !== 'number') return String(value)
  if (!Number.isFinite(value)) return ''
  if (Number.isInteger(value)) return value.toLocaleString('en-US')
  const size = Math.abs(value)
  if (size >= 1000) return value.toLocaleString('en-US', { maximumFractionDigits: 0 })
  if (size >= 100) return value.toFixed(1)
  if (size === 0) return '0'
  if (size < 0.0001) return value.toExponential(2)
  return String(Number(value.toPrecision(digits)))
}

export function fraction(value: any): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return ''
  return value.toFixed(3)
}

export function short(value: number): string {
  const size = Math.abs(value)
  if (size >= 1e9) return `${Number((value / 1e9).toPrecision(3))}B`
  if (size >= 1e6) return `${Number((value / 1e6).toPrecision(3))}M`
  if (size >= 1e4) return `${Number((value / 1e3).toPrecision(3))}k`
  return num(value, 3)
}

const MONTHS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]

export function gameDate(year: number): string {
  const whole = Math.floor(year + 1e-9)
  const day = Math.min(364, Math.floor((year - whole) * 365 + 1e-6))
  let month = 11
  while (MONTHS[month] > day) month -= 1
  return `${whole}-${two(month + 1)}-${two(day - MONTHS[month] + 1)}`
}

function two(value: number) {
  return String(value).padStart(2, '0')
}

export function time(value: any): string {
  if (!value) return ''
  const at = new Date(typeof value === 'number' ? value * 1000 : value)
  return `${at.getFullYear()}-${two(at.getMonth() + 1)}-${two(at.getDate())} ${two(at.getHours())}:${two(at.getMinutes())}:${two(at.getSeconds())}`
}

export function clock(value: any): string {
  return time(value).slice(5, 16)
}

export function span(seconds: number): string {
  if (!Number.isFinite(seconds)) return ''
  if (seconds < 90) return `${Math.round(seconds)} s`
  if (seconds < 5400) return `${Math.round(seconds / 60)} min`
  if (seconds < 172800) return `${(seconds / 3600).toFixed(1)} h`
  return `${(seconds / 86400).toFixed(1)} d`
}

export function median(values: number[]): number | null {
  const kept = values.filter((value) => value !== null && value !== undefined && Number.isFinite(value)).sort((a, b) => a - b)
  if (!kept.length) return null
  const middle = kept.length >> 1
  return kept.length % 2 ? kept[middle] : (kept[middle - 1] + kept[middle]) / 2
}

export function sum(values: number[]): number {
  return values.reduce((total, value) => total + (value || 0), 0)
}

export function colors(keys: string[]): Record<string, string> {
  return Object.fromEntries([...keys].sort().map((key, index) => [key, PALETTE[index % PALETTE.length]]))
}

export function groupBy<T>(rows: T[], key: (row: T) => string): Map<string, T[]> {
  const out = new Map<string, T[]>()
  for (const row of rows) {
    const name = key(row)
    if (!out.has(name)) out.set(name, [])
    out.get(name)!.push(row)
  }
  return out
}
