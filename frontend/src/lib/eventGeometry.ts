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

export function eventLine(metadata: Record<string, unknown>) {
  const point = (v: unknown): v is [number, number] =>
    Array.isArray(v) &&
    v.length === 2 &&
    v.every((n) => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1)
  const a = metadata.p1,
    b = metadata.p2
  return point(a) && point(b) && Math.hypot(a[0] - b[0], a[1] - b[1]) > 1e-6
    ? { x1: a[0] * 1000, y1: a[1] * 1000, x2: b[0] * 1000, y2: b[1] * 1000 }
    : null
}
