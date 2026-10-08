import type { Camera } from '@/api/cameras'

/** What the operator sees for a camera, derived from desired state + worker runtime. */
export type CameraDisplayState =
  | 'live'
  | 'connecting'
  | 'reconnecting'
  | 'degraded'
  | 'error'
  | 'stopping'
  | 'stopped'
  | 'no_worker'

export type Tone = 'normal' | 'warning' | 'critical' | 'neutral'

export const TONE: Record<CameraDisplayState, Tone> = {
  live: 'normal',
  connecting: 'neutral',
  reconnecting: 'critical',
  degraded: 'warning',
  error: 'critical',
  stopping: 'neutral',
  stopped: 'neutral',
  no_worker: 'warning',
}

export function cameraDisplayState(
  camera: Pick<Camera, 'enabled' | 'runtime'>,
): CameraDisplayState {
  const runtime = camera.runtime
  if (!camera.enabled) {
    return runtime && runtime.status !== 'STOPPED' ? 'stopping' : 'stopped'
  }
  if (!runtime) {
    return 'no_worker'
  }
  switch (runtime.status) {
    case 'RUNNING':
      return 'live'
    case 'DEGRADED':
      return 'degraded'
    case 'RECONNECTING':
      return 'reconnecting'
    case 'ERROR':
      return 'error'
    case 'STOPPING':
    case 'STOPPED':
      return 'stopping'
    case 'CREATED':
    case 'STARTING':
      return 'connecting'
  }
}

/** Seconds since the last frame, or null if no frame has been received. */
export function secondsSinceLastFrame(camera: Pick<Camera, 'runtime'>, now: number): number | null {
  const at = camera.runtime?.last_frame_at
  if (!at) {
    return null
  }
  return Math.max(0, Math.round((now - Date.parse(at)) / 1000))
}
