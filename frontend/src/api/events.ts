import type { components } from './generated'
import { apiGet, apiRequest, ApiError } from './http'

export type EventRead = components['schemas']['EventRead']
export type EventStatus = EventRead['status']
export type EventUpdate = components['schemas']['EventUpdate']
export type EventPage = components['schemas']['EventPage']

export interface EventFilters {
  cameraId?: string
  status?: string
  eventType?: string
  start?: string
  end?: string
}
export function eventParams(filters: EventFilters): URLSearchParams {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries({
    camera_id: filters.cameraId,
    status: filters.status,
    event_type: filters.eventType,
    start: filters.start,
    end: filters.end,
  })) {
    if (value) params.set(key, value)
  }
  return params
}

export function fetchEvents(
  cursor?: string,
  cameraId?: string,
  status?: string,
  signal?: AbortSignal,
  filters: EventFilters = {},
) {
  const params = eventParams({ ...filters, cameraId, status })
  params.set('limit', '50')
  if (cursor) params.set('cursor', cursor)
  if (cameraId) params.set('camera_id', cameraId)
  if (status) params.set('status', status)
  return apiGet<EventPage>(`/api/v1/events?${params}`, { signal })
}

export function fetchEvent(id: string, signal?: AbortSignal) {
  return apiGet<EventRead>(`/api/v1/events/${encodeURIComponent(id)}`, { signal })
}

// A live alarm can arrive while PostgreSQL is unavailable. Retry only the explicit 409.
export async function updateEvent(id: string, body: EventUpdate): Promise<EventRead> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await apiRequest<EventRead>('PATCH', `/api/v1/events/${id}`, { body })
    } catch (error) {
      if (
        !(error instanceof ApiError) ||
        error.code !== 'EVENT_NOT_PERSISTED_YET' ||
        attempt >= 4
      ) {
        throw error
      }
      await new Promise((resolve) => setTimeout(resolve, Math.min(500 * 2 ** attempt, 4000)))
    }
  }
}

// Only persisted matching rows, not merely the currently loaded cards/live alarms.
export async function exportEvents(filters: EventFilters, signal?: AbortSignal): Promise<void> {
  const response = await fetch(`/api/v1/events/export?${eventParams(filters)}`, {
    signal,
    headers: { Accept: 'text/csv' },
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new ApiError(
      response.status,
      data?.error?.code ?? 'HTTP_ERROR',
      data?.error?.message ?? response.statusText,
    )
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'events.csv'
  document.body.append(anchor)
  try {
    anchor.click()
  } finally {
    anchor.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}
