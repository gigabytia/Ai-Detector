import { expect, it } from 'vitest'
import { eventGeometry } from './eventGeometry'
it('maps saved normalized coordinates to the exact image viewBox', () => {
  expect(eventGeometry({ bbox: [0.1, 0.2, 0.5, 0.9], anchor: [0.3, 0.9] })).toEqual({
    bbox: { x: 100, y: 200, width: 400, height: 700 },
    anchor: { x: 300, y: 900 },
  })
})
it('does not render malformed or reversed geometry', () => {
  for (const bbox of [null, [0, 0, 2, 1], [0.9, 0, 0.1, 1], [NaN, 0, 1, 1], ['0', 0, 1, 1]]) {
    expect(eventGeometry({ bbox, anchor: [Infinity, 0] })).toEqual({ bbox: null, anchor: null })
  }
})
