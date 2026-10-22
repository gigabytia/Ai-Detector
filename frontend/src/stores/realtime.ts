import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import type { LiveEvent } from '@/lib/live/events'

export const useRealtimeStore = defineStore('realtime', () => {
  const connected = ref(false)
  const alarms = shallowRef<LiveEvent[]>([])
  const seen = new Set<string>()
  function receive(event: LiveEvent): boolean {
    if (seen.has(event.id)) return false
    seen.add(event.id)
    if (seen.size > 2000) seen.delete(seen.values().next().value!)
    alarms.value = [event, ...alarms.value.filter((e) => e.id !== event.id)].slice(0, 200)
    return true
  }
  function persisted(ids: Set<string>) {
    alarms.value = alarms.value.filter((e) => !ids.has(e.id))
  }
  return { connected, alarms, receive, persisted }
})
