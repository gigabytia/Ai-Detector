import type { components } from './generated'
import { apiGet, apiRequest } from './http'
export type Zone = components['schemas']['ZoneRead']
export type ZoneShape = components['schemas']['ZoneShape']
export type Point = { x: number; y: number }
const path = (cameraId: string) => `/api/v1/cameras/${cameraId}/zones`
export const fetchZones = (id: string, signal?: AbortSignal) => apiGet<Zone[]>(path(id), { signal })
export const saveZone = (cameraId: string, body: ZoneShape, id?: string) =>
  apiRequest<Zone>(id ? 'PUT' : 'POST', `${path(cameraId)}${id ? `/${id}` : ''}`, { body })
export const deleteZone = (cameraId: string, id: string) =>
  apiRequest<void>('DELETE', `${path(cameraId)}/${id}`)
