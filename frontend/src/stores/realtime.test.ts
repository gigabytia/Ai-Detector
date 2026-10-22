import { beforeEach, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useRealtimeStore } from './realtime'
import type { LiveEvent } from '@/lib/live/events'
beforeEach(() => setActivePinia(createPinia()))
const event = { id: 'event-1' } as LiveEvent
it('deduplicates retries and removes saved live cards', () => {
  const store = useRealtimeStore()
  expect(store.receive(event)).toBe(true)
  expect(store.receive(event)).toBe(false)
  expect(store.alarms).toHaveLength(1)
  store.persisted(new Set([event.id]))
  expect(store.alarms).toHaveLength(0)
  expect(store.receive(event)).toBe(false)
})
it('bounds retained volatile alarms', () => {
  const store = useRealtimeStore()
  for (let i = 0; i < 300; i++) store.receive({ ...event, id: String(i) })
  expect(store.alarms).toHaveLength(200)
})
