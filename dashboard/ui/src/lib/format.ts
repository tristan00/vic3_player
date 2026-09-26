import { clsx, type ClassValue } from 'clsx'
import type { Rate, Status } from '@/lib/api'

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export function n(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function compact(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e9) return `${(v / 1e9).toFixed(a >= 1e10 ? 0 : 1)}B`
  if (a >= 1e6) return `${(v / 1e6).toFixed(a >= 1e7 ? 0 : 1)}M`
  if (a >= 1e4) return `${(v / 1e3).toFixed(0)}K`
  if (a >= 1e3) return `${(v / 1e3).toFixed(1)}K`
  if (a >= 100 || Number.isInteger(v)) return n(v)
  return v.toLocaleString(undefined, { maximumSignificantDigits: 3 })
}

export function pct(r: Rate | null | undefined, digits = 0): string | null {
  if (!r || !r.of) return null
  const p = (100 * r.n) / r.of
  let places = digits
  while (r.n !== r.of && r.n !== 0 && places < 4 && (Number(p.toFixed(places)) === 100 || Number(p.toFixed(places)) === 0)) places++
  return `${p.toFixed(places)}%`
}

export function ms(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  if (v >= 10_000) return `${(v / 1000).toFixed(1)}s`
  return `${n(Math.round(v))}ms`
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`
  return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}m`
}

export function ago(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—'
  return `${duration((now - Date.parse(iso)) / 1000)} ago`
}

export function when(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const today = new Date()
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  if (d.toDateString() === today.toDateString()) return time
  return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${time}`
}

export const HOURS_PER_YEAR = 365 * 24

export function gameYears(hours: number): string {
  return `${(hours / HOURS_PER_YEAR).toFixed(1)}y`
}

export const STATUSES: Status[] = ['done', 'invalid', 'raced', 'no_object', 'ui_leftover']

export const STATUS_LABEL: Record<Status, string> = {
  done: 'done',
  invalid: 'invalid',
  raced: 'raced',
  no_object: 'no object',
  ui_leftover: 'ui left open',
}

export const STATUS_HELP: Record<Status, string> = {
  done: 'the executor ran it as valid and the next snapshot found no window left open',
  invalid: 'the executor reported the action as not valid',
  raced: 'a time control found the game already in the state it asked for',
  no_object: 'the executor could not find the game object the action names',
  ui_leftover: 'it ran, but a game window was still open at the next snapshot',
}

export const STATUS_FILL: Record<Status, string> = {
  done: 'var(--done)',
  invalid: 'var(--invalid)',
  raced: 'var(--raced)',
  no_object: 'var(--no-object)',
  ui_leftover: 'var(--ui-leftover)',
}

export function label(key: string): string {
  return key.replaceAll('_', ' ')
}
