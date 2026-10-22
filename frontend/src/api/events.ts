import type { components } from './generated'
import { apiGet, apiRequest, ApiError } from './http'

export type EventRead = components['schemas']['EventRead']
export type EventStatus = EventRead['status']
export type EventUpdate = components['schemas']['EventUpdate']
export type EventPage = components['schemas']['EventPage']

export function fetchEvents(
  cursor?: string,
  cameraId?: string,
  status?: string,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ limit: '50' })
  if (cursor) params.set('cursor', cursor)
  if (cameraId) params.set('camera_id', cameraId)
  if (status) params.set('status', status)
  return apiGet<EventPage>(`/api/v1/events?${params}`, { signal })
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
