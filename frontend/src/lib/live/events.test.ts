import { describe, expect, it } from 'vitest'
import { parseLiveEvent } from './events'
import { parseTelemetry } from '@/composables/useTelemetry'
const id = '11111111-1111-4111-8111-111111111111'
const event = {
  id,
  camera_id: id,
  run_id: id,
  zone_id: id,
  track_id: 1,
  type: 'PERSON_ENTERED_DANGER_ZONE',
  severity: 'critical',
  occurred_at: '2026-01-01T00:00:00Z',
  detector_confidence: 0.8,
  event_confidence: 0.7,
}
describe('live event contract', () => {
  it('accepts domain event', () => expect(parseLiveEvent(JSON.stringify(event))?.id).toBe(id))
  it.each([
    { ...event, track_id: 0 },
    { ...event, severity: 'bad' },
    { ...event, event_confidence: 2 },
    { ...event, camera_id: 'bad' },
    { ...event, occurred_at: 4 },
  ])('rejects malformed event', (value) => expect(parseLiveEvent(JSON.stringify(value))).toBeNull())
  it('ignores bad JSON', () => expect(parseLiveEvent('[')).toBeNull())
})
describe('selected camera telemetry', () => {
  const value = {
    version: 1,
    camera_id: id,
    run_id: id,
    frame_id: 1,
    persons: 2,
    persons_in_zone: 1,
    inference_ms: 10,
    captured_at: '2026-01-01T00:00:00Z',
  }
  it('accepts metadata without JPEG', () =>
    expect(parseTelemetry(JSON.stringify(value), id)?.persons).toBe(2))
  it('ignores another camera', () =>
    expect(parseTelemetry(JSON.stringify(value), 'other')).toBeNull())
  it('rejects invalid count', () =>
    expect(parseTelemetry(JSON.stringify({ ...value, persons: -1 }), id)).toBeNull())
})

it('accepts line crossing with line reference and rejects mixed/wrong references', () => {
  const crossing = { ...event, type: 'PERSON_CROSSED_LINE', zone_id: null, line_id: event.zone_id }
  expect(parseLiveEvent(JSON.stringify(crossing))?.type).toBe('PERSON_CROSSED_LINE')
  expect(parseLiveEvent(JSON.stringify({ ...crossing, line_id: null }))).toBeNull()
  expect(parseLiveEvent(JSON.stringify({ ...crossing, zone_id: event.zone_id }))).toBeNull()
})

it('accepts loitering as a zone alarm, not a line event', () => {
  const loiter = { ...event, type: 'PERSON_LOITERING_IN_DANGER_ZONE' }
  expect(parseLiveEvent(JSON.stringify(loiter))?.type).toBe(loiter.type)
  expect(parseLiveEvent(JSON.stringify({ ...loiter, zone_id: null }))).toBeNull()
  expect(parseLiveEvent(JSON.stringify({ ...loiter, line_id: event.zone_id }))).toBeNull()
})
