import { describe, expect, it } from 'vitest'

import type { SystemStatus } from '@/api/system'

import { summarizeSystemHealth } from './systemHealth'

const worker = {
  worker_id: 'w1',
  version: '0.1.0',
  started_at: '2026-01-01T12:00:00Z',
  last_seen_at: '2026-01-01T12:00:10Z',
  uptime_seconds: 10,
}

function status(overrides: Partial<SystemStatus> = {}): SystemStatus {
  return {
    status: 'ok',
    checked_at: '2026-01-01T12:00:10Z',
    dependencies: [
      { name: 'database', ok: true, error: null },
      { name: 'redis', ok: true, error: null },
    ],
    workers: [worker],
    ...overrides,
  }
}

describe('summarizeSystemHealth', () => {
  it('is down when the API request failed', () => {
    expect(summarizeSystemHealth(status(), true)).toBe('down')
  })

  it('is loading before the first response', () => {
    expect(summarizeSystemHealth(undefined, false)).toBe('loading')
  })

  it('is ok with all dependencies and a worker', () => {
    expect(summarizeSystemHealth(status(), false)).toBe('ok')
  })

  it('is degraded without workers', () => {
    expect(summarizeSystemHealth(status({ workers: [] }), false)).toBe('degraded')
  })

  it('is degraded when a dependency fails', () => {
    const dependencies = [{ name: 'redis', ok: false, error: 'ConnectionError' }]
    expect(summarizeSystemHealth(status({ dependencies }), false)).toBe('degraded')
  })
})
