// Historic event coordinates only. Never substitute the camera's current zone.
export function eventGeometry(metadata: Record<string, unknown>) {
  const unit = (v: unknown): v is number =>
    typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1
  const b = metadata.bbox
  const a = metadata.anchor
  const bbox =
    Array.isArray(b) && b.length === 4 && b.every(unit) && b[0]! <= b[2]! && b[1]! <= b[3]!
      ? {
          x: b[0]! * 1000,
          y: b[1]! * 1000,
          width: (b[2]! - b[0]!) * 1000,
          height: (b[3]! - b[1]!) * 1000,
        }
      : null
  const anchor =
    Array.isArray(a) && a.length === 2 && a.every(unit)
      ? { x: a[0]! * 1000, y: a[1]! * 1000 }
      : null
  return { bbox, anchor }
}
