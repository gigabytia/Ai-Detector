import { describe, expect, it } from 'vitest'
import { overlayPeople } from './overlay'
import type { PreviewMetadata, PersonTrack } from './protocol'

const detection = {
  bbox: [0.1, 0.2, 0.5, 0.9] as [number, number, number, number],
  confidence: 0.9,
}
const track: PersonTrack = {
  ...detection,
  track_id: 17,
  state: 'NORMAL',
  age: 2,
  hits: 2,
  missed_frames: 0,
}
function metadata(detections = [detection], tracks: PersonTrack[] = [track]): PreviewMetadata {
  return {
    version: 1,
    camera_id: 'a',
    run_id: 'r',
    frame_id: 1,
    captured_at: '2026-10-14T12:00:00Z',
    source_ts_ms: 100,
    width: 100,
    height: 100,
    inference_ms: 1,
    detections,
    tracks,
  }
}
describe('person overlay', () => {
  it('labels confirmed detections with their track ID', () => {
    expect(overlayPeople(metadata())[0]?.trackId).toBe(17)
  })
  it('never draws lost people on an empty frame', () => {
    expect(overlayPeople(metadata([], [{ ...track, state: 'LOST', missed_frames: 1 }]))).toEqual([])
  })
  it('does not invent IDs for candidates or use lost IDs', () => {
    expect(overlayPeople(metadata([detection], []))[0]?.trackId).toBeUndefined()
    expect(
      overlayPeople(metadata([detection], [{ ...track, state: 'LOST', missed_frames: 1 }]))[0]
        ?.trackId,
    ).toBeUndefined()
  })
  it('does not assign a track from a different box', () => {
    expect(
      overlayPeople(metadata([detection], [{ ...track, bbox: [0.6, 0.2, 0.9, 0.9] }]))[0]?.trackId,
    ).toBeUndefined()
  })
  it('keeps compatibility with M4 packets without tracks', () => {
    const old = metadata()
    delete old.tracks
    expect(overlayPeople(old)[0]?.trackId).toBeUndefined()
  })
})
