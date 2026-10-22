import type { components } from './generated'
import { apiGet } from './http'
export type Dashboard = components['schemas']['Dashboard']
export type TrackSession = components['schemas']['TrackSession']
export type TrackPage = components['schemas']['TrackPage']
export interface AnalyticsFilter {
  start: string
  end: string
  cameraId: string
}
export function analyticsParams(filter: AnalyticsFilter): URLSearchParams {
  const params = new URLSearchParams({ start: filter.start, end: filter.end })
  if (filter.cameraId) params.set('camera_id', filter.cameraId)
  return params
}
export function fetchDashboard(filter: AnalyticsFilter, signal?: AbortSignal): Promise<Dashboard> {
  return apiGet(`/api/v1/analytics?${analyticsParams(filter)}`, { signal })
}
export function fetchTracks(
  filter: AnalyticsFilter,
  cursor?: string,
  signal?: AbortSignal,
): Promise<TrackPage> {
  const params = analyticsParams(filter)
  if (cursor) params.set('cursor', cursor)
  return apiGet(`/api/v1/analytics/tracks?${params}`, { signal })
}
