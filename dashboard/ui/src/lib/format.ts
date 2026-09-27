import { clsx, type ClassValue } from 'clsx'

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export function n(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '∅'
  return v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function num(v: number): string {
  if (v === 0) return '0'
  if (Number.isInteger(v)) return v.toLocaleString()
  const a = Math.abs(v)
  if (a !== 0 && a < 0.001) return v.toPrecision(3)
  return v.toLocaleString(undefined, { maximumFractionDigits: a < 1 ? 4 : a < 1000 ? 3 : 1 })
}

export function compact(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '∅'
  const a = Math.abs(v)
  if (a >= 1e9) return `${(v / 1e9).toFixed(a >= 1e10 ? 0 : 1)}B`
  if (a >= 1e6) return `${(v / 1e6).toFixed(a >= 1e7 ? 0 : 1)}M`
  if (a >= 1e4) return `${(v / 1e3).toFixed(0)}K`
  if (a >= 1e3) return `${(v / 1e3).toFixed(1)}K`
  if (a >= 100 || Number.isInteger(v)) return n(v)
  return v.toLocaleString(undefined, { maximumSignificantDigits: 3 })
}

export function when(iso: string): string {
  const d = new Date(iso)
  return `${d.toLocaleDateString([], { year: 'numeric', month: '2-digit', day: '2-digit' })} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
}

export const HOURS_PER_YEAR = 365 * 24

export function label(key: string): string {
  return key.replaceAll('_', ' ')
}
