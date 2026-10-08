import { describe, expect, it } from 'vitest'

import type { CameraRuntime } from '@/api/cameras'

import { cameraDisplayState, secondsSinceLastFrame } from './cameraStatus'

function runtime(
  status: CameraRuntime['status'],
  extra: Partial<CameraRuntime> = {},
): CameraRuntime {
  return {
    status,
    capture_fps: 15,
    frame_size: [1280, 720],
    last_frame_at: '2026-01-01T12:00:00Z',
    last_error: null,
    reconnect_attempts: 0,
    last_reconnect_attempt_at: null,
    worker_id: 'w1',
    updated_at: '2026-01-01T12:00:00Z',
    ...extra,
  }
}

describe('cameraDisplayState', () => {
  it('shows a disabled camera as stopped, or stopping while the worker still reports it', () => {
    expect(cameraDisplayState({ enabled: false, runtime: null })).toBe('stopped')
    expect(cameraDisplayState({ enabled: false, runtime: runtime('RUNNING') })).toBe('stopping')
    expect(cameraDisplayState({ enabled: false, runtime: runtime('STOPPED') })).toBe('stopped')
  })

  it('reports a missing worker when an enabled camera has no runtime', () => {
    expect(cameraDisplayState({ enabled: true, runtime: null })).toBe('no_worker')
  })

  it.each([
    ['RUNNING', 'live'],
    ['STARTING', 'connecting'],
    ['CREATED', 'connecting'],
    ['RECONNECTING', 'reconnecting'],
    ['DEGRADED', 'degraded'],
    ['ERROR', 'error'],
    ['STOPPING', 'stopping'],
  ] as const)('maps runtime %s to %s', (status, expected) => {
    expect(cameraDisplayState({ enabled: true, runtime: runtime(status) })).toBe(expected)
  })
})

describe('secondsSinceLastFrame', () => {
  it('is null without frames and never negative', () => {
    const now = Date.parse('2026-01-01T12:00:05Z')
    expect(secondsSinceLastFrame({ runtime: null }, now)).toBeNull()
    expect(
      secondsSinceLastFrame({ runtime: runtime('RUNNING', { last_frame_at: null }) }, now),
    ).toBeNull()
    expect(secondsSinceLastFrame({ runtime: runtime('RUNNING') }, now)).toBe(5)
    expect(secondsSinceLastFrame({ runtime: runtime('RUNNING') }, now - 10_000)).toBe(0)
  })
})
