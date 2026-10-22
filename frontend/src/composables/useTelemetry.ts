import { onUnmounted, ref, shallowRef, watch, type Ref } from 'vue'

export interface Telemetry {
  version: 1
  camera_id: string
  run_id: string
  frame_id: number
  captured_at: string
  persons: number
  persons_in_zone: number
  inference_ms: number
}
export function parseTelemetry(raw: string, cameraId: string): Telemetry | null {
  try {
    const e = JSON.parse(raw)
    if (
      !e ||
      e.version !== 1 ||
      e.camera_id !== cameraId ||
      typeof e.run_id !== 'string' ||
      typeof e.captured_at !== 'string' ||
      !Number.isFinite(Date.parse(e.captured_at))
    )
      return null
    if (
      !['frame_id', 'persons', 'persons_in_zone'].every(
        (k) => Number.isSafeInteger(e[k]) && e[k] >= 0,
      ) ||
      typeof e.inference_ms !== 'number' ||
      !Number.isFinite(e.inference_ms) ||
      e.inference_ms < 0
    )
      return null
    return e as Telemetry
  } catch {
    return null
  }
}
export function useTelemetry(cameraId: Ref<string | undefined>) {
  const data = shallowRef<Telemetry | null>(null)
  const receivedAt = ref(0)
  let socket: WebSocket | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let generation = 0
  let delay = 500
  function clear() {
    generation++
    clearTimeout(timer)
    socket?.close()
    socket = undefined
    data.value = null
    receivedAt.value = 0
  }
  function connect(id: string, current: number) {
    if (current !== generation || typeof WebSocket === 'undefined') return
    const ws = new WebSocket(
      `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/live/cameras/${id}/telemetry`,
    )
    socket = ws
    ws.onmessage = (message) => {
      if (current !== generation || typeof message.data !== 'string') return
      const parsed = parseTelemetry(message.data, id)
      if (!parsed) return
      data.value = parsed
      receivedAt.value = Date.now()
      delay = 500
    }
    ws.onclose = () => {
      if (current === generation) {
        timer = setTimeout(() => connect(id, current), delay)
        delay = Math.min(delay * 2, 8000)
      }
    }
    ws.onerror = () => ws.close()
  }
  watch(
    cameraId,
    (id) => {
      clear()
      delay = 500
      if (id) connect(id, generation)
    },
    { immediate: true },
  )
  onUnmounted(clear)
  return { data, receivedAt }
}
