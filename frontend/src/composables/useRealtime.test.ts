import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { i18n } from '@/i18n'
import { useRealtimeStore } from '@/stores/realtime'
import { useRealtime } from './useRealtime'

class FakeEventSource {
  static last: FakeEventSource
  onopen?: () => void
  onerror?: () => void
  listeners = new Map<string, (event: { data: string }) => void>()
  close = vi.fn()
  constructor(readonly url: string) {
    FakeEventSource.last = this
  }
  addEventListener(kind: string, handler: (event: { data: string }) => void) {
    this.listeners.set(kind, handler)
  }
  emit(kind: string, value = {}) {
    this.listeners.get(kind)?.({ data: JSON.stringify(value) })
  }
}
const id = '11111111-1111-4111-8111-111111111111'
const alarm = {
  id,
  camera_id: id,
  run_id: id,
  zone_id: id,
  track_id: 1,
  type: 'PERSON_ENTERED_DANGER_ZONE',
  severity: 'critical',
  occurred_at: '2026-01-01T00:00:00Z',
  detector_confidence: 0.8,
  event_confidence: 0.7,
}
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.restoreAllMocks()
})
it('handles reconnect, DB-independent alarms, updates, fallback and unmount', () => {
  vi.useFakeTimers()
  vi.stubGlobal('EventSource', FakeEventSource)
  const client = new QueryClient()
  const pinia = createPinia()
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  const wrapper = mount(
    defineComponent({
      setup() {
        useRealtime()
        return () => null
      },
    }),
    { global: { plugins: [pinia, i18n, [VueQueryPlugin, { queryClient: client }]] } },
  )
  const source = FakeEventSource.last
  const store = useRealtimeStore(pinia)
  expect(source.url).toBe('/api/v1/events/stream')
  source.onopen?.()
  expect(store.connected).toBe(true)
  source.emit('event.created', alarm)
  source.emit('event.created', alarm)
  expect(store.alarms).toHaveLength(1)
  source.emit('event.updated', { id, status: 'ACKNOWLEDGED' })
  expect(store.alarms).toHaveLength(0)
  source.emit('unavailable')
  expect(store.connected).toBe(false)
  source.emit('resync')
  expect(store.connected).toBe(true)
  source.onerror?.()
  expect(store.connected).toBe(false)
  const before = invalidate.mock.calls.length
  vi.advanceTimersByTime(15000)
  expect(invalidate.mock.calls.length).toBeGreaterThan(before)
  wrapper.unmount()
  expect(source.close).toHaveBeenCalledOnce()
  const ended = invalidate.mock.calls.length
  vi.advanceTimersByTime(15000)
  expect(invalidate.mock.calls.length).toBe(ended)
  client.clear()
})
