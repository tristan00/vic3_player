import { useEffect, useRef, useState } from 'react'

export type Loaded<T> = { data?: T; error?: string; loading: boolean; reload: () => void }

const listeners = new Set<(up: boolean) => void>()
let reachable = true

function reached(up: boolean) {
  if (up !== reachable) {
    reachable = up
    listeners.forEach((listener) => listener(up))
  }
}

export async function request<T = any>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    reached(false)
    throw new Error('The dashboard server is not answering')
  }
  reached(true)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ? String(body.detail) : `${response.status} ${response.statusText}`)
  }
  return response.json()
}

export function useReachable() {
  const [up, setUp] = useState(reachable)
  useEffect(() => {
    listeners.add(setUp)
    return () => void listeners.delete(setUp)
  }, [])
  return up
}

export function useApi<T = any>(path: string | null, live = 0): Loaded<T> {
  const [state, setState] = useState<{ path: string | null; data?: T; error?: string; loading: boolean }>({ path, loading: path !== null })
  const [tick, setTick] = useState(0)
  const current = useRef(path)
  current.current = path
  useEffect(() => {
    if (path === null) return
    let cancelled = false
    const load = () =>
      request<T>(path).then(
        (data) => !cancelled && current.current === path && setState({ path, data, loading: false }),
        (error) => !cancelled && current.current === path && setState((before) => ({ path, data: before.path === path ? before.data : undefined, error: error.message, loading: false })),
      )
    setState((before) => (before.path === path ? before : { path, loading: true }))
    load()
    const timer = live ? window.setInterval(() => !document.hidden && load(), live) : 0
    return () => {
      cancelled = true
      if (timer) window.clearInterval(timer)
    }
  }, [path, live, tick])
  const fresh = state.path === path
  return { data: fresh ? state.data : undefined, error: fresh ? state.error : undefined, loading: !fresh || state.loading, reload: () => setTick((n) => n + 1) }
}
