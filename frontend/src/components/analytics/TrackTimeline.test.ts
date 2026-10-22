import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { i18n } from '@/i18n'
import TrackTimeline from './TrackTimeline.vue'
const track = {
  version: 1 as const,
  kind: 'track' as const,
  id: 'id',
  camera_id: 'cam',
  run_id: 'run',
  track_id: 7,
  started_at: '2026-01-01T00:00:00Z',
  ended_at: '2026-01-01T00:00:10Z',
  truncated: false,
  segments: [
    { state: 'NORMAL' as const, start: '2026-01-01T00:00:00Z', end: '2026-01-01T00:00:04Z' },
    {
      state: 'IN_DANGER_ZONE' as const,
      start: '2026-01-01T00:00:04Z',
      end: '2026-01-01T00:00:10Z',
    },
  ],
}
it('keeps a separate timeline with proportional states and readable exact times', () => {
  const w = mount(TrackTimeline, { props: { track }, global: { plugins: [i18n] } })
  expect(w.text()).toContain('Трек #7')
  expect(w.text()).toContain('В опасной зоне')
  const bars = w.findAll('span.absolute')
  expect(bars).toHaveLength(2)
  expect(bars[0]!.attributes('style')).toContain('width: 40%')
  expect(bars[1]!.attributes('style')).toContain('left: 40%')
  expect(w.find('details').exists()).toBe(true)
  w.unmount()
})
it('exposes truncated timelines without claiming the gap is normal', () => {
  const w = mount(TrackTimeline, {
    props: { track: { ...track, truncated: true } },
    global: { plugins: [i18n] },
  })
  expect(w.text()).toContain('часть таймлайна не сохранена')
  w.unmount()
})
