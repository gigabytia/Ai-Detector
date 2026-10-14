import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { fetchCameraConfig, saveCameraConfig, type CameraConfigRead } from '@/api/cameras'
import { i18n } from '@/i18n'

import CameraConfigPanel from './CameraConfigPanel.vue'

vi.mock('@/api/cameras', () => ({ fetchCameraConfig: vi.fn(), saveCameraConfig: vi.fn() }))
const config: CameraConfigRead = {
  overrides: { target_fps: null, detection_confidence: null },
  defaults: { target_fps: 10, detection_confidence: 0.25 },
  effective: { target_fps: 10, detection_confidence: 0.25 },
}
let client: QueryClient
beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  vi.mocked(fetchCameraConfig).mockResolvedValue(structuredClone(config))
  vi.mocked(saveCameraConfig).mockImplementation(async (_id, body) => ({
    ...config,
    overrides: body,
    effective: {
      target_fps: body.target_fps ?? 10,
      detection_confidence: body.detection_confidence ?? 0.25,
    },
  }))
})
afterEach(() => {
  client.clear()
  vi.clearAllMocks()
})
function render() {
  return mount(CameraConfigPanel, {
    props: { cameraId: 'a' },
    global: { plugins: [[VueQueryPlugin, { queryClient: client }], i18n] },
  })
}
it('saves actual number-input values and shows confirmation', async () => {
  const wrapper = render()
  await flushPromises()
  await wrapper.get('input[type=number]').setValue('4')
  await wrapper.get('input[id=confidence-a]').setValue('0.7')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(saveCameraConfig).toHaveBeenCalledWith('a', { target_fps: 4, detection_confidence: 0.7 })
  expect(wrapper.text()).toContain('Настройки сохранены')
  await wrapper.get('input[id=fps-a]').setValue('5')
  expect(wrapper.text()).not.toContain('Настройки сохранены')
  wrapper.unmount()
})
it('sends null overrides for blank inherited values', async () => {
  const wrapper = render()
  await flushPromises()
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(saveCameraConfig).toHaveBeenCalledWith('a', {
    target_fps: null,
    detection_confidence: null,
  })
  wrapper.unmount()
})
it('rejects values outside the domain even on programmatic submit', async () => {
  const wrapper = render()
  await flushPromises()
  await wrapper.get('input[id=fps-a]').setValue('99')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(saveCameraConfig).not.toHaveBeenCalled()
  expect(wrapper.get('[role=alert]').text()).toContain('от 1 до 30')
  wrapper.unmount()
})
