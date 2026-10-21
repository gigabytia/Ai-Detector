export interface Detection {
  bbox: [number, number, number, number]
  confidence: number
}
export interface PersonTrack extends Detection {
  track_id: number
  state: 'NORMAL' | 'LOST' | 'IN_DANGER_ZONE'
  age: number
  hits: number
  missed_frames: number
}
export interface PreviewMetadata {
  version: 1
  camera_id: string
  run_id: string
  frame_id: number
  captured_at: string
  source_ts_ms: number
  width: number
  height: number
  inference_ms: number
  detections: Detection[]
  tracks?: PersonTrack[]
  zones?: {
    id: string
    camera_id: string
    name: string
    enabled: boolean
    points: { x: number; y: number }[]
  }[]
}
export function parsePacket(
  data: ArrayBuffer,
  cameraId: string,
): { metadata: PreviewMetadata; jpeg: Blob } {
  if (data.byteLength < 6) throw new Error('Truncated preview packet')
  const size = new DataView(data).getUint32(0)
  if (size > 1_000_000 || size === 0 || size + 4 >= data.byteLength)
    throw new Error('Invalid preview header')
  const value: unknown = JSON.parse(new TextDecoder().decode(data.slice(4, 4 + size)))
  if (!value || typeof value !== 'object') throw new Error('Invalid preview metadata')
  const m = value as PreviewMetadata
  if (
    m.version !== 1 ||
    m.camera_id !== cameraId ||
    typeof m.run_id !== 'string' ||
    !Number.isInteger(m.frame_id) ||
    m.frame_id < 0 ||
    !Number.isFinite(m.width) ||
    m.width <= 0 ||
    !Number.isFinite(m.height) ||
    m.height <= 0 ||
    !Array.isArray(m.detections) ||
    !Number.isFinite(Date.parse(m.captured_at)) ||
    !Number.isFinite(m.inference_ms) ||
    !Number.isFinite(m.source_ts_ms)
  )
    throw new Error('Invalid preview metadata')
  for (const d of m.detections) {
    if (
      !d ||
      !Array.isArray(d.bbox) ||
      d.bbox.length !== 4 ||
      !d.bbox.every((n) => Number.isFinite(n) && n >= 0 && n <= 1) ||
      d.bbox[2] <= d.bbox[0] ||
      d.bbox[3] <= d.bbox[1] ||
      !Number.isFinite(d.confidence) ||
      d.confidence < 0 ||
      d.confidence > 1
    )
      throw new Error('Invalid detection')
  }
  if (m.tracks !== undefined) {
    if (!Array.isArray(m.tracks)) throw new Error('Invalid tracks')
    const ids = new Set<number>()
    for (const track of m.tracks) {
      if (
        !track ||
        !Number.isSafeInteger(track.track_id) ||
        track.track_id < 1 ||
        ids.has(track.track_id) ||
        !['NORMAL', 'LOST', 'IN_DANGER_ZONE'].includes(track.state) ||
        !Number.isSafeInteger(track.age) ||
        track.age < 1 ||
        !Number.isSafeInteger(track.hits) ||
        track.hits < 1 ||
        track.hits > track.age ||
        !Number.isSafeInteger(track.missed_frames) ||
        track.missed_frames < 0 ||
        track.missed_frames >= track.age ||
        (track.state !== 'LOST' ? track.missed_frames !== 0 : track.missed_frames === 0) ||
        !Array.isArray(track.bbox) ||
        track.bbox.length !== 4 ||
        !track.bbox.every((n) => Number.isFinite(n) && n >= 0 && n <= 1) ||
        track.bbox[2] <= track.bbox[0] ||
        track.bbox[3] <= track.bbox[1] ||
        !Number.isFinite(track.confidence) ||
        track.confidence < 0 ||
        track.confidence > 1
      )
        throw new Error('Invalid track')
      ids.add(track.track_id)
    }
  }
  if (m.zones !== undefined) {
    if (!Array.isArray(m.zones) || m.zones.length > 16) throw new Error('Invalid zones')
    const ids = new Set<string>()
    for (const z of m.zones) {
      if (
        !z ||
        typeof z.id !== 'string' ||
        ids.has(z.id) ||
        z.camera_id !== cameraId ||
        typeof z.name !== 'string' ||
        typeof z.enabled !== 'boolean' ||
        !Array.isArray(z.points) ||
        z.points.length < 3 ||
        z.points.length > 64 ||
        !z.points.every(
          (p) =>
            p &&
            Number.isFinite(p.x) &&
            Number.isFinite(p.y) &&
            p.x >= 0 &&
            p.x <= 1 &&
            p.y >= 0 &&
            p.y <= 1,
        )
      )
        throw new Error('Invalid zone')
      ids.add(z.id)
    }
  }
  return { metadata: m, jpeg: new Blob([data.slice(4 + size)], { type: 'image/jpeg' }) }
}
