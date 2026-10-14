import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { WsPreviewSource } from './source'

class FakeSocket {
  static instances: FakeSocket[] = []
  binaryType = ''
  onmessage: ((event: MessageEvent<unknown>) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  constructor(public url: string) {
    FakeSocket.instances.push(this)
  }
  close = vi.fn(() => this.onclose?.())
}
beforeEach(() => {
  vi.useFakeTimers()
  FakeSocket.instances = []
  vi.stubGlobal('WebSocket', FakeSocket)
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('preview source lifecycle', () => {
  it('connects once, uses same-origin path and closes on stop', () => {
    const state = vi.fn()
    const source = new WsPreviewSource('abc', vi.fn(), state)
    source.start()
    source.start()
    expect(FakeSocket.instances).toHaveLength(1)
    const socket = FakeSocket.instances[0]!
    expect(socket.url).toContain('/live/cameras/abc/preview')
    expect(socket.binaryType).toBe('arraybuffer')
    source.stop()
    expect(socket.close).toHaveBeenCalledOnce()
    vi.advanceTimersByTime(20_000)
    expect(FakeSocket.instances).toHaveLength(1)
    expect(state).toHaveBeenLastCalledWith('stopped')
  })
  it('reconnects after a closed connection and cancels pending retry on stop', () => {
    const source = new WsPreviewSource('abc', vi.fn(), vi.fn())
    source.start()
    FakeSocket.instances[0]!.onclose?.()
    vi.advanceTimersByTime(500)
    expect(FakeSocket.instances).toHaveLength(2)
    FakeSocket.instances[1]!.onclose?.()
    source.stop()
    vi.advanceTimersByTime(20_000)
    expect(FakeSocket.instances).toHaveLength(2)
  })
  it('ignores late messages from a replaced socket', () => {
    const onFrame = vi.fn()
    const source = new WsPreviewSource('abc', onFrame, vi.fn())
    source.start()
    const old = FakeSocket.instances[0]!
    old.onclose?.()
    vi.advanceTimersByTime(500)
    old.onmessage?.(new MessageEvent('message', { data: new ArrayBuffer(4) }))
    expect(onFrame).not.toHaveBeenCalled()
    source.stop()
  })
})
