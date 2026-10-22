import { expect, it } from 'vitest'
import { analyticsParams } from '@/api/analytics'
import { eventTrend, peopleTrend, eventBars } from './analytics'
import { fixture } from './analyticsFixture'
it('encodes an exact UTC window and camera without changing scope', () => {
  const p = analyticsParams({ start: fixture.start, end: fixture.end, cameraId: 'camera/a' })
  expect(p.get('camera_id')).toBe('camera/a')
  expect(p.get('end')).toBe(fixture.end)
  expect(
    analyticsParams({ start: fixture.start, end: fixture.end, cameraId: '' }).has('camera_id'),
  ).toBe(false)
})
it('never fills missing occupancy with zero or connects its gaps', () => {
  const option = peopleTrend(fixture, ['Всего', 'Зона'])
  const series = option.series as { data: unknown[][]; connectNulls: boolean }[]
  expect(series[0]!.data).toEqual([
    [fixture.events_over_time[0]!.at, 2],
    [fixture.events_over_time[1]!.at, null],
    [fixture.events_over_time[2]!.at, null],
  ])
  expect(series[0]!.connectNulls).toBe(false)
})
it('plots event zeros and counts in separate, zero-based axes', () => {
  const option = eventTrend(fixture, 'События')
  expect((option.series as { data: unknown[][] }[])[0]!.data[1]![1]).toBe(0)
  expect((option.yAxis as { min: number }).min).toBe(0)
  const bars = eventBars(['<script>'], [2], 'События')
  expect((bars.tooltip as { renderMode: string }).renderMode).toBe('richText')
})
