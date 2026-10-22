// Validate the fields used by the UI. Transport data never becomes trusted HTML.
export interface LiveEvent {
  id: string
  camera_id: string
  run_id: string
  track_id: number
  zone_id: string
  type: 'PERSON_ENTERED_DANGER_ZONE'
  severity: 'critical' | 'warning' | 'info'
  occurred_at: string
  detector_confidence: number
  event_confidence: number
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
export function parseLiveEvent(raw: string): LiveEvent | null {
  try {
    const e = JSON.parse(raw)
    if (
      !e ||
      !['id', 'camera_id', 'run_id', 'zone_id'].every(
        (k) => typeof e[k] === 'string' && uuid.test(e[k]),
      )
    )
      return null
    if (
      e.type !== 'PERSON_ENTERED_DANGER_ZONE' ||
      !['critical', 'warning', 'info'].includes(e.severity)
    )
      return null
    if (
      !Number.isSafeInteger(e.track_id) ||
      e.track_id < 1 ||
      typeof e.occurred_at !== 'string' ||
      !Number.isFinite(Date.parse(e.occurred_at))
    )
      return null
    if (
      !['detector_confidence', 'event_confidence'].every(
        (k) => typeof e[k] === 'number' && Number.isFinite(e[k]) && e[k] >= 0 && e[k] <= 1,
      )
    )
      return null
    return e as LiveEvent
  } catch {
    return null
  }
}
