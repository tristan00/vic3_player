import assert from 'node:assert/strict'
import { setImmediate } from 'node:timers/promises'
import test from 'node:test'
import { latestRequest } from '../src/lib/requests.ts'
import { watchConnection, watchStamp } from '../src/lib/live.ts'

test('live updates let the initial load finish and coalesce into one refresh', async (t) => {
  const pending = []
  t.mock.method(globalThis, 'fetch', (url, { signal }) => new Promise((resolve) => pending.push({ url, signal, resolve })))
  const received = []
  const request = latestRequest('/runs', (data) => received.push(data), assert.fail)
  t.after(request.dispose)
  const loaded = request.refresh()
  for (let i = 0; i < 10; i++) void request.refresh()
  assert.equal(pending.length, 1)
  assert.equal(pending[0].signal.aborted, false)
  pending[0].resolve(Response.json('first'))
  await setImmediate()
  assert.deepEqual(received, ['first'])
  assert.equal(pending.length, 2)
  pending[1].resolve(Response.json('latest'))
  await loaded
  assert.deepEqual(received, ['first', 'latest'])
  assert.equal(pending.length, 2)
})

test('navigation discards an old response and cancels its queued refresh', async (t) => {
  let finish
  const fetch = t.mock.method(globalThis, 'fetch', () => new Promise((resolve) => { finish = resolve }))
  const request = latestRequest('/old', assert.fail, assert.fail)
  const loaded = request.refresh()
  void request.refresh()
  request.dispose()
  finish(Response.json('stale'))
  await loaded
  await request.refresh()
  assert.equal(fetch.mock.callCount(), 1)
})

test('failed requests report an error and can refresh successfully', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'unavailable' }, { status: 503 }))
  const received = []
  const errors = []
  const request = latestRequest('/runs', (data) => received.push(data), (error) => errors.push(error))
  t.after(request.dispose)
  await request.refresh()
  fetch.mock.mockImplementation(async () => Response.json('recovered'))
  await request.refresh()
  assert.deepEqual(errors, ['unavailable'])
  assert.deepEqual(received, ['recovered'])
})

test('live polling is shared, emits changes, and stops while hidden or unsubscribed', async (t) => {
  const original = globalThis.document
  const document = Object.assign(new EventTarget(), { hidden: false })
  globalThis.document = document
  t.after(() => { globalThis.document = original })
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let stamp = 'one'
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json(stamp))
  const changes = []
  const status = []
  const stopStamp = watchStamp((value) => changes.push(value))
  const stopConnection = watchConnection((value) => status.push(value))
  t.after(() => { stopStamp(); stopConnection() })
  await setImmediate()
  assert.equal(fetch.mock.callCount(), 1)
  assert.deepEqual(changes, [])
  assert.equal(status.at(-1), true)
  t.mock.timers.tick(3000)
  await setImmediate()
  assert.equal(fetch.mock.callCount(), 2)
  assert.deepEqual(changes, [])
  document.hidden = true
  document.dispatchEvent(new Event('visibilitychange'))
  t.mock.timers.tick(9000)
  await setImmediate()
  assert.equal(fetch.mock.callCount(), 2)
  stamp = 'two'
  document.hidden = false
  document.dispatchEvent(new Event('visibilitychange'))
  await setImmediate()
  assert.deepEqual(changes, ['two'])
  assert.equal(fetch.mock.callCount(), 3)
  stopStamp()
  stopConnection()
  t.mock.timers.tick(9000)
  await setImmediate()
  assert.equal(fetch.mock.callCount(), 3)
})
