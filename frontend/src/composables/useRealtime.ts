import { useQueryClient } from '@tanstack/vue-query'
import { onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'
import { parseLiveEvent } from '@/lib/live/events'
import { useRealtimeStore } from '@/stores/realtime'

// One EventSource for the whole app. It reconnects natively. REST fills reconnect gaps.
export function useRealtime() {
  const client = useQueryClient()
  const store = useRealtimeStore()
  const { t } = useI18n()
  let source: EventSource | undefined
  let timer: ReturnType<typeof setInterval> | undefined
  let lastCameraRefresh = 0
  const resync = () => {
    void client.invalidateQueries({ queryKey: ['events'] })
    void client.invalidateQueries({ queryKey: ['cameras'] })
  }
  onMounted(() => {
    if (typeof EventSource !== 'undefined') {
      source = new EventSource('/api/v1/events/stream')
      source.onopen = () => {
        store.connected = true
        resync()
      }
      source.onerror = () => {
        store.connected = false
      }
      source.addEventListener('resync', () => {
        store.connected = true
        resync()
      })
      source.addEventListener('unavailable', () => {
        store.connected = false
      })
      source.addEventListener('event.updated', (message) => {
        try {
          const value = JSON.parse((message as MessageEvent).data)
          if (
            typeof value?.id === 'string' &&
            ['NEW', 'ACKNOWLEDGED', 'FALSE_POSITIVE'].includes(value.status)
          )
            store.persisted(new Set([value.id]))
        } catch {
          /* An invalid notification never changes state. */
        }
        void client.invalidateQueries({ queryKey: ['events'] })
      })
      source.addEventListener('event.created', (message) => {
        const event = parseLiveEvent((message as MessageEvent).data)
        if (!event) return
        if (store.receive(event))
          toast.warning(t('events.entered'), {
            description: t('events.track', { n: event.track_id }),
          })
        void client.invalidateQueries({ queryKey: ['events'] })
      })
      source.addEventListener('camera.status', () => {
        if (Date.now() - lastCameraRefresh < 1000) return
        lastCameraRefresh = Date.now()
        void client.invalidateQueries({ queryKey: ['cameras'] })
      })
    }
    // Live notifications are best effort. Periodic REST also covers lost status updates.
    timer = setInterval(resync, 15_000)
  })
  onUnmounted(() => {
    source?.close()
    clearInterval(timer)
    store.connected = false
  })
}
