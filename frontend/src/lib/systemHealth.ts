import type { SystemStatus } from '@/api/system'

export type SystemHealthLevel = 'ok' | 'degraded' | 'down' | 'loading'

/** Collapses the system status into one level the operator can read at a glance. */
export function summarizeSystemHealth(
  status: SystemStatus | undefined,
  requestFailed: boolean,
): SystemHealthLevel {
  if (requestFailed) return 'down'
  if (status === undefined) return 'loading'
  const dependenciesOk = status.dependencies.every((item) => item.ok)
  return dependenciesOk && status.workers.length > 0 ? 'ok' : 'degraded'
}
