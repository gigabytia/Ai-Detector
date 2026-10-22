import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { i18n } from '@/i18n'
import type { EventRead } from '@/api/events'
import EventSnapshot from './EventSnapshot.vue'
const event = {
  id: 'a',
  snapshot_url: '/api/v1/snapshots/a',
  snapshot_width: 1280,
  snapshot_height: 720,
  metadata: { bbox: [0.1, 0.2, 0.5, 0.9], anchor: [0.3, 0.9] },
} as unknown as EventRead
function render(value = event) {
  return mount(EventSnapshot, { props: { event: value }, global: { plugins: [i18n] } })
}
it('renders original image with aligned historic overlay only after load; toggle leaves image intact', async () => {
  const wrapper = render()
  expect(wrapper.find('svg').exists()).toBe(false)
  await wrapper.get('img').trigger('load')
  expect(wrapper.get('rect').attributes('width')).toBe('400')
  expect(wrapper.get('img').attributes('src')).toBe(event.snapshot_url)
  await wrapper.get('input').setValue(false)
  expect(wrapper.find('svg').exists()).toBe(false)
  expect(wrapper.find('img').exists()).toBe(true)
})
it('handles expired files and permits a fresh image request', async () => {
  const wrapper = render()
  await wrapper.get('img').trigger('error')
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.text()).toContain('недоступен')
  await wrapper.get('button').trigger('click')
  expect(wrapper.get('img').attributes('src')).toContain('?retry=1')
  await wrapper.get('img').trigger('load')
  expect(wrapper.find('svg').exists()).toBe(true)
})
it('shows an explicit placeholder for old/disabled events and resets on navigation', async () => {
  const wrapper = render({ ...event, snapshot_url: null })
  expect(wrapper.text()).toContain('не сохранён')
  expect(wrapper.find('img').exists()).toBe(false)
  await wrapper.setProps({ event })
  expect(wrapper.get('img').attributes('src')).toBe(event.snapshot_url)
})

it('uses saved line geometry, even when current camera geometry changes', async () => {
  const wrapper = render({
    ...event,
    type: 'PERSON_CROSSED_LINE',
    metadata: { ...event.metadata, p1: [0.2, 0.5], p2: [0.8, 0.5], direction: 'LEFT_TO_RIGHT' },
  })
  await wrapper.get('img').trigger('load')
  const line = wrapper.get('[data-historic-line]')
  expect(line.attributes('x1')).toBe('200')
  expect(line.attributes('x2')).toBe('800')
  expect(line.attributes('y1')).toBe('500')
})
