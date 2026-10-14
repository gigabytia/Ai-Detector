import { onScopeDispose, shallowRef, watch, type Ref } from 'vue'

import { WsPreviewSource, type ConnectionState, type PreviewFrame } from '@/lib/live/source'

/** Per-camera shallow state; bitmap resources are explicitly released on replacement/unmount. */
export function useCameraLive(cameraId: Ref<string>, active: Ref<boolean>) {
  const frame = shallowRef<PreviewFrame | null>(null)
  const state = shallowRef<ConnectionState>('stopped')
  const receivedAt = shallowRef(0)
  const clearFrame = () => {
    frame.value?.image.close()
    frame.value = null
    receivedAt.value = 0
  }
  const stop = watch(
    [cameraId, active],
    ([id, enabled], _, cleanup) => {
      clearFrame()
      if (!enabled) {
        state.value = 'stopped'
        return
      }
      const source = new WsPreviewSource(
        id,
        (next) => {
          frame.value?.image.close()
          frame.value = next
          receivedAt.value = Date.now()
        },
        (value) => {
          state.value = value
        },
      )
      source.start()
      cleanup(() => source.stop())
    },
    { immediate: true },
  )
  onScopeDispose(() => {
    stop()
    clearFrame()
  })
  return { frame, state, receivedAt }
}
