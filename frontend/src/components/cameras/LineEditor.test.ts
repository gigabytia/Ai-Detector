import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { fetchLines, saveLine, deleteLine, type Line } from '@/api/lines'
import type { Point } from '@/api/zones'
import { ApiError } from '@/api/http'
import { i18n } from '@/i18n'
import LineEditor from './LineEditor.vue'
vi.mock('@/api/lines', () => ({ fetchLines: vi.fn(), saveLine: vi.fn(), deleteLine: vi.fn() }))
const points = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
]
const line: Line = {
  id: 'z1',
  camera_id: 'a',
  name: 'Проход',
  enabled: true,
  p1: points[0]!,
  p2: points[1]!,
  created_at: '2026-10-21T00:00:00Z',
  updated_at: '2026-10-21T00:00:00Z',
}
let client: QueryClient
beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  vi.mocked(fetchLines).mockResolvedValue([])
  vi.mocked(saveLine).mockResolvedValue(line)
  vi.mocked(deleteLine).mockResolvedValue(undefined)
})
afterEach(() => {
  client.clear()
  vi.clearAllMocks()
})
function render() {
  return mount(
    defineComponent({
      components: { LineEditor },
      setup() {
        return { points: ref<Point[]>([]), editing: ref(false) }
      },
      template: '<LineEditor camera-id="a" v-model:points="points" v-model:editing="editing" />',
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }], i18n] } },
  )
}
function button(wrapper: ReturnType<typeof render>, text: string) {
  const b = wrapper.findAll('button').find((b) => b.text() === text)
  if (!b) throw Error(`Button missing: ${text}`)
  return b
}
it('creates a normalized directed segment from keyboard coordinates', async () => {
  const w = render()
  await flushPromises()
  await button(w, 'Добавить линию').trigger('click')
  for (const p of points) {
    const inputs = w.findAll('input[type=number]')
    await inputs[0]!.setValue(p.x)
    await inputs[1]!.setValue(p.y)
    await button(w, 'Добавить точку').trigger('click')
  }
  await w.get('form').trigger('submit')
  await flushPromises()
  expect(saveLine).toHaveBeenCalledWith(
    'a',
    { name: 'Линия пересечения', enabled: true, p1: points[0]!, p2: points[1]! },
    undefined,
  )
  expect(w.text()).toContain('Линия сохранена')
  w.unmount()
})
it('edits only the selected first line, preserving additional lines', async () => {
  vi.mocked(fetchLines).mockResolvedValue([line, { ...line, id: 'z2' }])
  const w = render()
  await flushPromises()
  expect(w.text()).toContain('несколько линий')
  await button(w, 'Изменить линию').trigger('click')
  await w.get('input[maxlength]').setValue('Новая')
  await w.get('form').trigger('submit')
  await flushPromises()
  expect(saveLine).toHaveBeenCalledWith(
    'a',
    { name: 'Новая', enabled: true, p1: points[0]!, p2: points[1]! },
    'z1',
  )
  expect(deleteLine).not.toHaveBeenCalled()
  w.unmount()
})
it('cancels without writing and reloads the original endpoints on re-entry', async () => {
  vi.mocked(fetchLines).mockResolvedValue([line])
  const w = render()
  await flushPromises()
  await button(w, 'Изменить линию').trigger('click')
  await button(w, 'Очистить').trigger('click')
  await button(w, 'Отмена').trigger('click')
  expect(saveLine).not.toHaveBeenCalled()
  await button(w, 'Изменить линию').trigger('click')
  expect(w.text()).toContain('Точки: 2 / 2')
  w.unmount()
})
it('validates minimum points before sending and keeps a rejected draft', async () => {
  const w = render()
  await flushPromises()
  await button(w, 'Добавить линию').trigger('click')
  await w.get('form').trigger('submit')
  expect(saveLine).not.toHaveBeenCalled()
  expect(w.get('[role=alert]').text()).toContain('две разные точки')
  w.unmount()
  vi.mocked(fetchLines).mockResolvedValue([line])
  vi.mocked(saveLine).mockRejectedValue(new ApiError(422, 'VALIDATION_ERROR', 'bad line'))
  const w2 = render()
  await flushPromises()
  await button(w2, 'Изменить линию').trigger('click')
  await w2.get('form').trigger('submit')
  await flushPromises()
  expect(w2.find('form').exists()).toBe(true)
  expect(w2.text()).toContain('Точки: 2 / 2')
  expect(w2.get('[role=alert]').text()).toContain('две разные точки')
  w2.unmount()
})
it('requires a separate confirmation before deletion', async () => {
  vi.mocked(fetchLines).mockResolvedValue([line])
  const w = render()
  await flushPromises()
  await button(w, 'Удалить линию').trigger('click')
  expect(deleteLine).not.toHaveBeenCalled()
  await button(w, 'Подтвердить удаление').trigger('click')
  await flushPromises()
  expect(deleteLine).toHaveBeenCalledWith('a', 'z1')
  w.unmount()
})
it('offers retry when line loading fails', async () => {
  vi.mocked(fetchLines).mockRejectedValue(new Error('offline'))
  const w = render()
  await flushPromises()
  expect(w.get('[role=alert]').text()).toContain('Не удалось загрузить линии')
  vi.mocked(fetchLines).mockResolvedValue([])
  await button(w, 'Повторить').trigger('click')
  await flushPromises()
  expect(w.text()).toContain('Линия ещё не задана')
  w.unmount()
})
it('does not retarget a dirty draft when the server list changes', async () => {
  vi.mocked(fetchLines).mockResolvedValue([line])
  const w = render()
  await flushPromises()
  await button(w, 'Изменить линию').trigger('click')
  client.setQueryData(['lines', 'a'], [{ ...line, id: 'z2', name: 'Другой' }])
  await flushPromises()
  await w.get('form').trigger('submit')
  await flushPromises()
  expect(saveLine).toHaveBeenCalledWith(
    'a',
    { name: 'Проход', enabled: true, p1: points[0]!, p2: points[1]! },
    'z1',
  )
  w.unmount()
})
it('shows a connection error without discarding the draft', async () => {
  vi.mocked(fetchLines).mockResolvedValue([line])
  vi.mocked(saveLine).mockRejectedValue(new Error('offline'))
  const w = render()
  await flushPromises()
  await button(w, 'Изменить линию').trigger('click')
  await w.get('form').trigger('submit')
  await flushPromises()
  expect(w.get('[role=alert]').text()).toContain('Нет связи с сервером')
  expect(w.text()).toContain('Точки: 2 / 2')
  w.unmount()
})
