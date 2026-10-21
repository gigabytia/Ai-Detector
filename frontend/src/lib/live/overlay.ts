import type { Detection, PreviewMetadata } from './protocol'

export interface OverlayPerson extends Detection {
  trackId?: number
}

// Lost tracks retain their last observation, not a box belonging to the current image.
// Candidates still show a detection without an invented ID until ByteTrack confirms them.
export function overlayPeople(metadata: PreviewMetadata): OverlayPerson[] {
  return metadata.detections.map((detection) => {
    const track = metadata.tracks?.find(
      (t) =>
        t.state === 'NORMAL' &&
        t.bbox.every((value, i) => Math.abs(value - detection.bbox[i]!) < 0.000001),
    )
    return { ...detection, trackId: track?.track_id }
  })
}
