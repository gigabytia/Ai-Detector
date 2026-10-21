import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { fetchZones, saveZone, deleteZone, type Zone, type Point } from '@/api/zones'
import { ApiError } from '@/api/http'
import { i18n } from '@/i18n'
import ZoneEditor from './ZoneEditor.vue'
vi.mock('@/api/zones', () => ({ fetchZones: vi.fn(), saveZone: vi.fn(), deleteZone: vi.fn() }))
const points = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 1, y: 1 },
]
const zone: Zone = {
  id: 'z1',
  camera_id: 'a',
  name: 'Проход',
  enabled: true,
  points,
  created_at: '2026-10-21T00:00:00Z',
  updated_at: '2026-10-21T00:00:00Z',
}
let client: QueryClient
beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  vi.mocked(fetchZones).mockResolvedValue([])
  vi.mocked(saveZone).mockResolvedValue(zone)
  vi.mocked(deleteZone).mockResolvedValue(undefined)
})
afterEach(() => {
  client.clear()
  vi.clearAllMocks()
})
function render() {
  return mount(
    defineComponent({
      components: { ZoneEditor },
      setup() {
        return { points: ref<Point[]>([]), editing: ref(false) }
      },
      template: '<ZoneEditor camera-id="a" v-model:points="points" v-model:editing="editing" />',
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }], i18n] } },
  )
}
function button(wrapper: ReturnType<typeof render>, text: string) {
  const b = wrapper.findAll('button').find((b) => b.text() === text)
  if (!b) throw Error(`Button missing: ${text}`)
  return b
}
it('creates a normalized polygon from keyboard coordinates', async () => {
  const w = render()
  await flushPromises()
  await button(w, 'Добавить зону').trigger('click')
  for (const p of points) {
    const inputs = w.findAll('input[type=number]')
    await inputs[0]!.setValue(p.x)
    await inputs[1]!.setValue(p.y)
    await button(w, 'Добавить точку').trigger('click')
  }
  await w.get('form').trigger('submit')
  await flushPromises()
  expect(saveZone).toHaveBeenCalledWith(
    'a',
    { name: 'Опасная зона', enabled: true, points },
    undefined,
  )
  expect(w.text()).toContain('Зона сохранена')
  w.unmount()
})
it('edits only the selected first zone, preserving additional zones', async () => {
  vi.mocked(fetchZones).mockResolvedValue([zone, { ...zone, id: 'z2' }])
  const w = render()
  await flushPromises()
  expect(w.text()).toContain('несколько зон')
  await button(w, 'Изменить зону').trigger('click')
  await w.get('input[maxlength]').setValue('Новая')
  await w.get('form').trigger('submit')
  await flushPromises()
  expect(saveZone).toHaveBeenCalledWith('a', { name: 'Новая', enabled: true, points }, 'z1')
  expect(deleteZone).not.toHaveBeenCalled()
  w.unmount()
})
it('cancels without writing and reloads the original points on re-entry', async () => {
  vi.mocked(fetchZones).mockResolvedValue([zone])
  const w = render()
  await flushPromises()
  await button(w, 'Изменить зону').trigger('click')
  await button(w, 'Очистить точки').trigger('click')
  await button(w, 'Отмена').trigger('click')
  expect(saveZone).not.toHaveBeenCalled()
  await button(w, 'Изменить зону').trigger('click')
  expect(w.text()).toContain('Вершин: 3')
  w.unmount()
})
it('validates minimum points before sending and keeps a rejected draft', async () => {
  const w = render()
  await flushPromises()
  await button(w, 'Добавить зону').trigger('click')
  await w.get('form').trigger('submit')
  expect(saveZone).not.toHaveBeenCalled()
  expect(w.get('[role=alert]').text()).toContain('3–64')
  w.unmount()
  vi.mocked(fetchZones).mockResolvedValue([zone])
  vi.mocked(saveZone).mockRejectedValue(new ApiError(422, 'VALIDATION_ERROR', 'bad polygon'))
  const w2 = render()
  await flushPromises()
  await button(w2, 'Изменить зону').trigger('click')
  await w2.get('form').trigger('submit')
  await flushPromises()
  expect(w2.find('form').exists()).toBe(true)
  expect(w2.text()).toContain('Вершин: 3')
  expect(w2.get('[role=alert]').text()).toContain('самопересечения')
  w2.unmount()
})
it('requires a separate confirmation before deletion', async () => {
  vi.mocked(fetchZones).mockResolvedValue([zone])
  const w = render()
  await flushPromises()
  await button(w, 'Удалить зону').trigger('click')
  expect(deleteZone).not.toHaveBeenCalled()
  await button(w, 'Подтвердите удаление').trigger('click')
  await flushPromises()
  expect(deleteZone).toHaveBeenCalledWith('a', 'z1')
  w.unmount()
})
it('offers retry when zone loading fails', async () => {
  vi.mocked(fetchZones).mockRejectedValue(new Error('offline'))
  const w = render()
  await flushPromises()
  expect(w.get('[role=alert]').text()).toContain('Не удалось загрузить зону')
  vi.mocked(fetchZones).mockResolvedValue([])
  await button(w, 'Повторить').trigger('click')
  await flushPromises()
  expect(w.text()).toContain('Зона не задана')
  w.unmount()
})
it('does not retarget a dirty draft when the server list changes', async () => {
  vi.mocked(fetchZones).mockResolvedValue([zone])
  const w = render()
  await flushPromises()
  await button(w, 'Изменить зону').trigger('click')
  client.setQueryData(['zones', 'a'], [{ ...zone, id: 'z2', name: 'Другой' }])
  await flushPromises()
  await w.get('form').trigger('submit')
  await flushPromises()
  expect(saveZone).toHaveBeenCalledWith('a', { name: 'Проход', enabled: true, points }, 'z1')
  w.unmount()
})
it('shows a connection error without discarding the draft', async () => {
  vi.mocked(fetchZones).mockResolvedValue([zone])
  vi.mocked(saveZone).mockRejectedValue(new Error('offline'))
  const w = render()
  await flushPromises()
  await button(w, 'Изменить зону').trigger('click')
  await w.get('form').trigger('submit')
  await flushPromises()
  expect(w.get('[role=alert]').text()).toContain('Нет связи с сервером')
  expect(w.text()).toContain('Вершин: 3')
  w.unmount()
})
