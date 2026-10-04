import { getJSON } from './requests.ts'

const INTERVAL_MS = 3000
const listeners = new Set<(stamp: string) => void>()
const connections = new Set<(connected: boolean) => void>()
let stamp: string | null = null
let connected = false
let watching = false
let controller: AbortController | null = null
let timer: ReturnType<typeof setTimeout> | null = null

function setConnected(value: boolean) {
  if (connected === value) return
  connected = value
  connections.forEach((receive) => receive(value))
}

async function poll() {
  if (controller || document.hidden || !watching) return
  const current = new AbortController()
  controller = current
  try {
    const next = await getJSON<string>('/api/stamp', AbortSignal.any([current.signal, AbortSignal.timeout(10000)]))
    if (current.signal.aborted) return
    setConnected(true)
    if (stamp !== null && stamp !== next) listeners.forEach((receive) => receive(next))
    stamp = next
  } catch {
    if (!current.signal.aborted) setConnected(false)
  } finally {
    if (controller === current) {
      controller = null
      timer = setTimeout(() => { timer = null; void poll() }, INTERVAL_MS)
    }
  }
}

function update() {
  const needed = listeners.size + connections.size > 0
  if (needed !== watching) {
    watching = needed
    if (watching) document.addEventListener('visibilitychange', update)
    else document.removeEventListener('visibilitychange', update)
  }
  if (!watching || document.hidden) {
    if (timer) clearTimeout(timer)
    timer = null
    controller?.abort()
    controller = null
    setConnected(false)
  } else if (!timer) {
    void poll()
  }
}

export function watchStamp(receive: (stamp: string) => void) {
  listeners.add(receive)
  update()
  return () => { listeners.delete(receive); update() }
}

export function watchConnection(receive: (connected: boolean) => void) {
  connections.add(receive)
  receive(connected)
  update()
  return () => { connections.delete(receive); update() }
}
