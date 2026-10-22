import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { i18n } from '@/i18n'
import { fetchEvents, exportEvents } from '@/api/events'
import { ApiError } from '@/api/http'
import EventsView from './EventsView.vue'
vi.mock('@/api/events', () => ({ fetchEvents: vi.fn(), exportEvents: vi.fn() }))
vi.mock('@/composables/useCameras', () => ({
  useCameras: () => ({ data: ref([{ id: 'cam', name: 'Камера' }]) }),
}))
vi.mock('@/components/events/EventCard.vue', () => ({
  default: { props: ['event'], template: '<article>{{event.type}}</article>' },
}))
let client: QueryClient
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.mocked(fetchEvents).mockResolvedValue({ items: [], next_cursor: null })
  vi.mocked(exportEvents).mockResolvedValue()
})
afterEach(() => {
  client.clear()
  vi.clearAllMocks()
})
function render() {
  return mount(EventsView, {
    global: { plugins: [[VueQueryPlugin, { queryClient: client }], createPinia(), i18n] },
  })
}
it('exports full current camera/status/type/period filters and shows progress', async () => {
  const w = render()
  await flushPromises()
  const selects = w.findAll('select')
  await selects[0]!.setValue('cam')
  await selects[1]!.setValue('FALSE_POSITIVE')
  await selects[2]!.setValue('PERSON_LOITERING_IN_DANGER_ZONE')
  await selects[3]!.setValue(24)
  await flushPromises()
  await w
    .findAll('button')
    .find((b) => b.text() === 'Скачать CSV')!
    .trigger('click')
  await flushPromises()
  const filters = vi.mocked(exportEvents).mock.calls[0]![0]
  expect(filters).toMatchObject({
    cameraId: 'cam',
    status: 'FALSE_POSITIVE',
    eventType: 'PERSON_LOITERING_IN_DANGER_ZONE',
  })
  expect(Date.parse(filters.end!) - Date.parse(filters.start!)).toBe(86400000)
  expect(vi.mocked(fetchEvents).mock.calls.at(-1)![4]).toMatchObject({
    eventType: filters.eventType,
    start: filters.start,
    end: filters.end,
  })
  w.unmount()
})
it('explains oversize without presenting a partial success and allows retry', async () => {
  vi.mocked(exportEvents).mockRejectedValueOnce(new ApiError(422, 'EXPORT_TOO_LARGE', 'narrow'))
  const w = render()
  await flushPromises()
  const button = w.findAll('button').find((b) => b.text() === 'Скачать CSV')!
  await button.trigger('click')
  await flushPromises()
  expect(w.get('[role=alert]').text()).toContain('Файл не обрезается')
  await button.trigger('click')
  await flushPromises()
  expect(w.find('[role=alert]').exists()).toBe(false)
  w.unmount()
})
