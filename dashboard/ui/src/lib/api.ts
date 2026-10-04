import { useCallback, useEffect, useRef, useState } from 'react'
import type { components } from '@/api/schema'
import { latestRequest } from './requests'
import { watchConnection, watchStamp } from './live'

export type S = components['schemas']
export type Grid = S['Grid']
export type GridColumn = S['GridColumn']
export type Cell = S['Cell']
export type Ref = S['Ref']
export type Series = S['Series']

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
  const request = useRef<ReturnType<typeof latestRequest<T>> | null>(null)

  useEffect(() => {
    if (!url) return
    const current = latestRequest<T>(url,
      (data) => setState({ url, data, error: null }),
      (error) => setState((s) => ({ url, data: s.url === url ? s.data : null, error })))
    request.current = current
    return () => {
      current.dispose()
      request.current = null
    }
  }, [url])

  useEffect(() => {
    void request.current?.refresh()
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

export function useStamp(live: boolean): string {
  const [stamp, setStamp] = useState('')
  useEffect(() => {
    if (!live) return
    return watchStamp(setStamp)
  }, [live])
  return stamp
}

export function useConnected(): boolean {
  const [c, setC] = useState(false)
  useEffect(() => watchConnection(setC), [])
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
