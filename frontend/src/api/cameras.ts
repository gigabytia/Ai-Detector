import type { components } from './generated'
import { apiGet, apiRequest } from './http'

export type Camera = components['schemas']['CameraRead']
export type CameraRuntime = components['schemas']['CameraRuntimeRead']
export type CameraCreate = components['schemas']['CameraCreate']
export type CameraUpdate = components['schemas']['CameraUpdate']
export type SourceType = components['schemas']['SourceType']
export type Upload = components['schemas']['UploadRead']

export type CameraAction = 'start' | 'stop' | 'restart'

export function fetchCameras(signal?: AbortSignal): Promise<Camera[]> {
  return apiGet<Camera[]>('/api/v1/cameras', { signal })
}

export function createCamera(body: CameraCreate): Promise<Camera> {
  return apiRequest<Camera>('POST', '/api/v1/cameras', { body })
}

export function updateCamera(id: string, body: CameraUpdate): Promise<Camera> {
  return apiRequest<Camera>('PATCH', `/api/v1/cameras/${id}`, { body })
}

export function deleteCamera(id: string): Promise<void> {
  return apiRequest<void>('DELETE', `/api/v1/cameras/${id}`)
}

export function runCameraAction(id: string, action: CameraAction): Promise<Camera> {
  return apiRequest<Camera>('POST', `/api/v1/cameras/${id}/${action}`)
}

export function uploadVideo(file: File): Promise<Upload> {
  const form = new FormData()
  form.append('file', file)
  return apiRequest<Upload>('POST', '/api/v1/uploads', { body: form })
}
