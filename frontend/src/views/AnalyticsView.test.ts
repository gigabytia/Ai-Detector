import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { i18n } from '@/i18n'
import { fetchDashboard, fetchTracks } from '@/api/analytics'
import { fixture } from '@/lib/analyticsFixture'
import AnalyticsView from './AnalyticsView.vue'
vi.mock('@/api/analytics', () => ({ fetchDashboard: vi.fn(), fetchTracks: vi.fn() }))
vi.mock('@/components/analytics/AnalyticsChart.vue', () => ({
  default: { props: ['label', 'option'], template: '<div role="img" :aria-label="label" />' },
}))
let client: QueryClient
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.mocked(fetchDashboard).mockResolvedValue(fixture)
  vi.mocked(fetchTracks).mockResolvedValue({ items: [], next_cursor: null })
})
afterEach(() => {
  client.clear()
  vi.clearAllMocks()
})
function render() {
  return mount(AnalyticsView, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient: client }], i18n],
      stubs: { RouterLink: true },
    },
  })
}
it('shows real KPIs with explicit completed-track and sampled occupancy semantics', async () => {
  const w = render()
  await flushPromises()
  expect(w.text()).toContain('Завершённые треки людей')
  expect(w.text()).toContain('Это треки внутри камеры')
  expect(w.findAll('[role=img]')).toHaveLength(3)
  expect(w.text()).toContain('Выберите одну камеру')
  w.unmount()
})
it('changes camera and window in both queries without blending results', async () => {
  const w = render()
  await flushPromises()
  const selects = w.findAll('select')
  await selects[0]!.setValue(1)
  await selects[1]!.setValue('cam')
  await flushPromises()
  const call = vi.mocked(fetchDashboard).mock.calls.at(-1)![0]
  expect(call.cameraId).toBe('cam')
  expect(Date.parse(call.end) - Date.parse(call.start)).toBe(3600000)
  expect(vi.mocked(fetchTracks).mock.calls.at(-1)![0].cameraId).toBe('cam')
  const before = vi.mocked(fetchDashboard).mock.calls.length
  await w
    .findAll('button')
    .find((b) => b.text() === 'Обновить период')!
    .trigger('click')
  await flushPromises()
  // Manual refresh must discover cameras added while the dashboard stayed open.
  expect(
    vi
      .mocked(fetchDashboard)
      .mock.calls.slice(before)
      .some(([f]) => !f.cameraId),
  ).toBe(true)
  w.unmount()
})
it('reports errors rather than manufacturing zero cards and supports retry', async () => {
  vi.mocked(fetchDashboard).mockRejectedValue(new Error('offline'))
  const w = render()
  await flushPromises()
  expect(w.get('[role=alert]').text()).toContain('не заменяются нулями')
  expect(w.findAll('article')).toHaveLength(0)
  vi.mocked(fetchDashboard).mockResolvedValue(fixture)
  await w
    .findAll('button')
    .find((b) => b.text() === 'Повторить')!
    .trigger('click')
  await flushPromises()
  expect(w.text()).toContain('Всего событий')
  w.unmount()
})
