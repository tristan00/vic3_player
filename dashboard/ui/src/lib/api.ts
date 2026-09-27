import { useCallback, useEffect, useRef, useState } from 'react'
import type { components } from '@/api/schema'

export type S = components['schemas']
export type Grid = S['Grid']
export type GridColumn = S['GridColumn']
export type Cell = S['Cell']
export type Ref = S['Ref']
export type Series = S['Series']

const THROTTLE_MS = 3000
const RECONNECT_MS = 3000

async function getJSON<T>(url: string, signal: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal, headers: { accept: 'application/json' } })
  if (!r.ok) {
    let detail = `HTTP ${r.status}`
    try {
      const body = await r.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      detail = `HTTP ${r.status} ${r.statusText}`
    }
    throw new Error(detail)
  }
  return (await r.json()) as T
}

export interface Loaded<T> {
  data: T | null
  error: string | null
  loading: boolean
  stale: boolean
  reload: () => void
}

export function useApi<T>(url: string | null, opts: { live?: boolean } = {}): Loaded<T> {
  const [state, setState] = useState<{ url: string | null; data: T | null; error: string | null }>({ url: null, data: null, error: null })
  const [nonce, setNonce] = useState(0)
  const stamp = useStamp(opts.live ?? false)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  useEffect(() => {
    if (!url) return
    const ac = new AbortController()
    getJSON<T>(url, ac.signal)
      .then((data) => {
        if (alive.current) setState({ url, data, error: null })
      })
      .catch((e: unknown) => {
        if (!alive.current || (e as Error)?.name === 'AbortError') return
        setState((s) => ({ url, data: s.url === url ? s.data : null, error: (e as Error)?.message ?? 'request failed' }))
      })
    return () => ac.abort()
  }, [url, nonce, stamp])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return {
    data: state.data,
    error: state.url === url ? state.error : null,
    loading: state.data === null && state.error === null,
    stale: state.url !== url && state.data !== null,
    reload,
  }
}

let source: EventSource | null = null
const listeners = new Set<(s: string) => void>()
let lastEmit = 0
let pending: string | null = null
let timer: ReturnType<typeof setTimeout> | null = null
let connected = false
const connectionListeners = new Set<(c: boolean) => void>()

function emit(s: string) {
  lastEmit = Date.now()
  listeners.forEach((fn) => fn(s))
}

function onStamp(s: string) {
  const wait = lastEmit + THROTTLE_MS - Date.now()
  if (wait <= 0) return emit(s)
  pending = s
  if (!timer)
    timer = setTimeout(() => {
      timer = null
      if (pending !== null) emit(pending)
      pending = null
    }, wait)
}

function setConnected(c: boolean) {
  connected = c
  connectionListeners.forEach((fn) => fn(c))
}

function ensureSource() {
  if (source) return
  const src = new EventSource('/api/events')
  source = src
  src.addEventListener('open', () => setConnected(true))
  src.addEventListener('stamp', (ev) => onStamp((ev as MessageEvent).data ?? ''))
  src.addEventListener('error', () => {
    setConnected(false)
    if (src.readyState !== EventSource.CLOSED) return
    source = null
    setTimeout(ensureSource, RECONNECT_MS)
  })
}

export function useStamp(live: boolean): string {
  const [stamp, setStamp] = useState('')
  useEffect(() => {
    if (!live) return
    ensureSource()
    listeners.add(setStamp)
    return () => {
      listeners.delete(setStamp)
    }
  }, [live])
  return stamp
}

export function useConnected(): boolean {
  const [c, setC] = useState(connected)
  useEffect(() => {
    ensureSource()
    connectionListeners.add(setC)
    return () => {
      connectionListeners.delete(setC)
    }
  }, [])
  return c
}

export function qs(params: Record<string, string | number | boolean | string[] | null | undefined>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x))
    else if (v !== null && v !== undefined && v !== '' && v !== false) p.set(k, String(v))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}
