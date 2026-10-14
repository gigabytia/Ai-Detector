import { effectScope, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { PreviewFrame } from '@/lib/live/source'

const { instances } = vi.hoisted(() => ({
  instances: [] as {
    cameraId: string
    onFrame: (value: PreviewFrame) => void
    start: ReturnType<typeof vi.fn>
    stop: ReturnType<typeof vi.fn>
  }[],
}))
vi.mock('@/lib/live/source', () => ({
  WsPreviewSource: class {
    start = vi.fn()
    stop = vi.fn()
    constructor(
      public cameraId: string,
      public onFrame: (value: PreviewFrame) => void,
    ) {
      instances.push(this)
    }
  },
}))
import { useCameraLive } from './useCameraLive'

function frame(): PreviewFrame {
  return {
    image: { close: vi.fn() } as unknown as ImageBitmap,
    metadata: {} as PreviewFrame['metadata'],
  }
}
afterEach(() => {
  instances.length = 0
})

describe('per-camera live state', () => {
  it('does not subscribe while hidden or stopped', () => {
    const scope = effectScope()
    scope.run(() => useCameraLive(ref('a'), ref(false)))
    expect(instances).toHaveLength(0)
    scope.stop()
  })
  it('starts and stops with visibility', async () => {
    const scope = effectScope()
    const active = ref(false)
    scope.run(() => useCameraLive(ref('a'), active))
    active.value = true
    await nextTick()
    expect(instances[0]!.start).toHaveBeenCalledOnce()
    active.value = false
    await nextTick()
    expect(instances[0]!.stop).toHaveBeenCalledOnce()
    scope.stop()
  })
  it('releases replaced bitmaps and final frame on disposal', () => {
    const scope = effectScope()
    scope.run(() => useCameraLive(ref('a'), ref(true)))
    const first = frame()
    const second = frame()
    instances[0]!.onFrame(first)
    instances[0]!.onFrame(second)
    expect(first.image.close).toHaveBeenCalledOnce()
    scope.stop()
    expect(second.image.close).toHaveBeenCalledOnce()
  })
  it('clears old frames when changing camera', async () => {
    const scope = effectScope()
    const id = ref('a')
    const state = scope.run(() => useCameraLive(id, ref(true)))!
    const value = frame()
    instances[0]!.onFrame(value)
    id.value = 'b'
    await nextTick()
    expect(value.image.close).toHaveBeenCalledOnce()
    expect(state.frame.value).toBeNull()
    expect(instances[0]!.stop).toHaveBeenCalledOnce()
    expect(instances[1]!.cameraId).toBe('b')
    scope.stop()
  })
  it('does not share a global frame between cameras', () => {
    const scope = effectScope()
    const states = scope.run(() => [
      useCameraLive(ref('a'), ref(true)),
      useCameraLive(ref('b'), ref(true)),
    ])!
    instances[0]!.onFrame(frame())
    expect(states[0]!.frame.value).not.toBeNull()
    expect(states[1]!.frame.value).toBeNull()
    scope.stop()
  })
})
