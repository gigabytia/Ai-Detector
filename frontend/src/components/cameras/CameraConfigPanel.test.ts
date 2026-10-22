import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { fetchCameraConfig, saveCameraConfig, type CameraConfigRead } from '@/api/cameras'
import { i18n } from '@/i18n'

import CameraConfigPanel from './CameraConfigPanel.vue'

vi.mock('@/api/cameras', () => ({ fetchCameraConfig: vi.fn(), saveCameraConfig: vi.fn() }))
const timingDefaults = {
  loitering_threshold_seconds: 10,
  snapshot_enabled: true,
  zone_enter_dwell_seconds: 0.25,
  zone_exit_grace_seconds: 0.5,
  event_cooldown_seconds: 3,
}
const timingOverrides = {
  loitering_threshold_seconds: null,
  snapshot_enabled: null,
  zone_enter_dwell_seconds: null,
  zone_exit_grace_seconds: null,
  event_cooldown_seconds: null,
}
const config: CameraConfigRead = {
  overrides: { target_fps: null, detection_confidence: null, ...timingOverrides },
  defaults: { target_fps: 10, detection_confidence: 0.25, ...timingDefaults },
  effective: { target_fps: 10, detection_confidence: 0.25, ...timingDefaults },
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
      ...timingDefaults,
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
  expect(saveCameraConfig).toHaveBeenCalledWith('a', {
    target_fps: 4,
    detection_confidence: 0.7,
    ...timingOverrides,
  })
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
    ...timingOverrides,
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

it('preserves and edits zone timing overrides with detection settings', async () => {
  vi.mocked(fetchCameraConfig).mockResolvedValue({
    ...config,
    overrides: { ...config.overrides, zone_enter_dwell_seconds: 2 },
  })
  const wrapper = render()
  await flushPromises()
  expect((wrapper.get('#zone_enter_dwell_seconds-a').element as HTMLInputElement).value).toBe('2')
  await wrapper.get('#event_cooldown_seconds-a').setValue('6')
  await wrapper.get('#loitering_threshold_seconds-a').setValue('1.5')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(saveCameraConfig).toHaveBeenCalledWith('a', {
    target_fps: null,
    detection_confidence: null,
    loitering_threshold_seconds: 1.5,
    zone_enter_dwell_seconds: 2,
    zone_exit_grace_seconds: null,
    event_cooldown_seconds: 6,
    snapshot_enabled: null,
  })
  wrapper.unmount()
})

it('persists snapshot on/off override and resets it to inheritance', async () => {
  const wrapper = render()
  await flushPromises()
  await wrapper.get('select[id=snapshot-a]').setValue('false')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(saveCameraConfig).toHaveBeenLastCalledWith(
    'a',
    expect.objectContaining({ snapshot_enabled: false }),
  )
  const reset = wrapper.findAll('button').find((b) => b.text().includes('Сбросить'))!
  await reset.trigger('click')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(saveCameraConfig).toHaveBeenLastCalledWith(
    'a',
    expect.objectContaining({ snapshot_enabled: null }),
  )
})
