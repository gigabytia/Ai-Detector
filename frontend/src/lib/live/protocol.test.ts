import { describe, expect, it } from 'vitest'

import { parsePacket } from './protocol'

const metadata = {
  version: 1,
  camera_id: 'camera-1',
  run_id: 'run-1',
  frame_id: 123,
  captured_at: '2026-10-14T12:00:00Z',
  source_ts_ms: 1000,
  width: 1280,
  height: 720,
  inference_ms: 12.5,
  detections: [{ bbox: [0.1, 0.1, 0.8, 0.9], confidence: 0.95 }],
}
function packet(header: unknown = metadata) {
  const text = new TextEncoder().encode(JSON.stringify(header))
  const data = new ArrayBuffer(text.byteLength + 8)
  new DataView(data).setUint32(0, text.byteLength)
  new Uint8Array(data).set(text, 4)
  new Uint8Array(data).set([255, 216, 255, 217], 4 + text.length)
  return data
}
describe('preview protocol', () => {
  it('keeps JPEG and its exact metadata in one message', () => {
    const parsed = parsePacket(packet(), 'camera-1')
    expect(parsed.metadata).toEqual(metadata)
    expect(parsed.jpeg.type).toBe('image/jpeg')
    expect(parsed.jpeg.size).toBe(4)
  })
  it('accepts empty detections', () => {
    expect(
      parsePacket(packet({ ...metadata, detections: [] }), 'camera-1').metadata.detections,
    ).toEqual([])
  })
  it('rejects a different camera', () => {
    expect(() => parsePacket(packet(), 'camera-2')).toThrow()
  })
  it.each([0, 4, 5])('rejects truncated packets (%s bytes)', (size) => {
    expect(() => parsePacket(new ArrayBuffer(size), 'camera-1')).toThrow()
  })
  it('rejects a header longer than its message', () => {
    const value = packet()
    new DataView(value).setUint32(0, 2_000_000)
    expect(() => parsePacket(value, 'camera-1')).toThrow()
  })
  it.each([
    { version: 2 },
    { frame_id: -1 },
    { width: 0 },
    { height: -1 },
    { captured_at: 'invalid' },
    { inference_ms: null },
    { detections: {} },
    { detections: [{ bbox: [0, 0, 1.1, 1], confidence: 0.9 }] },
    { detections: [{ bbox: [0.5, 0, 0.1, 1], confidence: 0.9 }] },
    { detections: [{ bbox: [0, 0, 1, 1], confidence: 2 }] },
  ])('rejects malformed metadata %j', (patch) => {
    expect(() => parsePacket(packet({ ...metadata, ...patch }), 'camera-1')).toThrow()
  })
})

const track = {
  track_id: 17,
  bbox: [0.1, 0.1, 0.8, 0.9],
  confidence: 0.95,
  state: 'NORMAL',
  age: 4,
  hits: 4,
  missed_frames: 0,
}
describe('person tracking protocol', () => {
  it('accepts tracks and retained lost observations', () => {
    const tracks = [track, { ...track, track_id: 18, state: 'LOST', hits: 2, missed_frames: 2 }]
    expect(parsePacket(packet({ ...metadata, tracks }), 'camera-1').metadata.tracks).toEqual(tracks)
  })
  it('accepts an empty registry', () => {
    expect(parsePacket(packet({ ...metadata, tracks: [] }), 'camera-1').metadata.tracks).toEqual([])
  })
  it.each([
    { track_id: -1 },
    { track_id: 0 },
    { track_id: 1.5 },
    { state: 'unknown' },
    { age: 0 },
    { hits: 5 },
    { missed_frames: 1 },
    { state: 'LOST' },
    { bbox: [0, 0, 1.1, 1] },
    { confidence: null },
  ])('rejects invalid track %j', (patch) => {
    expect(() =>
      parsePacket(packet({ ...metadata, tracks: [{ ...track, ...patch }] }), 'camera-1'),
    ).toThrow()
  })
  it('rejects duplicate IDs in the same frame', () => {
    expect(() => parsePacket(packet({ ...metadata, tracks: [track, track] }), 'camera-1')).toThrow()
  })
})

const zone = {
  id: 'z',
  camera_id: 'camera-1',
  name: 'Zone',
  enabled: true,
  points: [
    { x: 0, y: 0 },
    { x: 1, y: 0 },
    { x: 1, y: 1 },
  ],
}
it('accepts zones and danger tracks in the atomic frame header', () => {
  expect(
    parsePacket(
      packet({ ...metadata, zones: [zone], tracks: [{ ...track, state: 'IN_DANGER_ZONE' }] }),
      'camera-1',
    ).metadata.zones,
  ).toEqual([zone])
})
it.each([
  { ...zone, camera_id: 'other' },
  { ...zone, points: [] },
  { ...zone, points: [{ x: 2, y: 0 }, ...zone.points] },
  { ...zone, enabled: 1 },
])('rejects invalid zone %j', (bad) => {
  expect(() => parsePacket(packet({ ...metadata, zones: [bad] }), 'camera-1')).toThrow()
})

it('accepts directed finite line and rejects invalid line metadata', () => {
  const line = {
    id: 'l1',
    camera_id: 'cam',
    name: 'Линия',
    enabled: true,
    p1: { x: 0.2, y: 0.5 },
    p2: { x: 0.8, y: 0.5 },
  }
  const packet = (lines: unknown) => {
    const header = new TextEncoder().encode(
      JSON.stringify({ ...metadata, camera_id: 'cam', lines }),
    )
    const result = new Uint8Array(4 + header.length + 2)
    new DataView(result.buffer).setUint32(0, header.length)
    result.set(header, 4)
    result.set([255, 216], 4 + header.length)
    return result.buffer
  }
  expect(parsePacket(packet([line]), 'cam').metadata.lines?.[0]?.name).toBe('Линия')
  for (const lines of [
    [{ ...line, p2: line.p1 }],
    [line, line],
    [{ ...line, p1: { x: 2, y: 0 } }],
    [{ ...line, camera_id: 'other' }],
  ])
    expect(() => parsePacket(packet(lines), 'cam')).toThrow()
})
