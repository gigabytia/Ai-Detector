export interface Detection {
  bbox: [number, number, number, number]
  confidence: number
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
  return { metadata: m, jpeg: new Blob([data.slice(4 + size)], { type: 'image/jpeg' }) }
}
