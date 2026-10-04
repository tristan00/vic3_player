export async function getJSON<T>(url: string, signal: AbortSignal): Promise<T> {
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

export function latestRequest<T>(url: string, receive: (data: T) => void, fail: (message: string) => void) {
  const controller = new AbortController()
  let running = false
  let pending = false

  async function refresh() {
    if (controller.signal.aborted) return
    if (running) {
      pending = true
      return
    }
    running = true
    do {
      pending = false
      try {
        const data = await getJSON<T>(url, controller.signal)
        if (!controller.signal.aborted) receive(data)
      } catch (error) {
        if (!controller.signal.aborted) fail((error as Error)?.message ?? 'request failed')
      }
    } while (pending && !controller.signal.aborted)
    running = false
  }

  return { refresh, dispose: () => controller.abort() }
}
