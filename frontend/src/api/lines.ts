import type { components } from './generated'
import { apiGet, apiRequest } from './http'
export type Line = components['schemas']['LineRead']
export type LineShape = components['schemas']['LineShape']
const path = (id: string) => `/api/v1/cameras/${id}/lines`
export const fetchLines = (id: string, signal?: AbortSignal) => apiGet<Line[]>(path(id), { signal })
export const saveLine = (camera: string, body: LineShape, id?: string) =>
  apiRequest<Line>(id ? 'PUT' : 'POST', `${path(camera)}${id ? `/${id}` : ''}`, { body })
export const deleteLine = (camera: string, id: string) =>
  apiRequest<void>('DELETE', `${path(camera)}/${id}`)
