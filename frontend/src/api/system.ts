import type { components } from './generated'
import { apiGet } from './http'

export type SystemStatus = components['schemas']['SystemStatusRead']

export function fetchSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  return apiGet<SystemStatus>('/api/v1/system/status', { signal })
}
