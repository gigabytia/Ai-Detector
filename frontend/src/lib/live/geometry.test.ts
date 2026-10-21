import { expect, it } from 'vitest'
import { imagePoint } from './geometry'
it('maps portrait image points, rejecting black side bars', () => {
  expect(imagePoint(200, 100, 400, 200, 100, 200)).toEqual({ x: 0.5, y: 0.5 })
  expect(imagePoint(150, 0, 400, 200, 100, 200)).toEqual({ x: 0, y: 0 })
  expect(imagePoint(149, 100, 400, 200, 100, 200)).toBeNull()
  expect(imagePoint(251, 100, 400, 200, 100, 200)).toBeNull()
})
it('maps landscape image points and rejects top padding', () => {
  expect(imagePoint(100, 100, 200, 200, 400, 200)).toEqual({ x: 0.5, y: 0.5 })
  expect(imagePoint(0, 49, 200, 200, 400, 200)).toBeNull()
  expect(imagePoint(200, 150, 200, 200, 400, 200)).toEqual({ x: 1, y: 1 })
})
it('rejects invalid viewports', () => {
  expect(imagePoint(1, 1, 0, 1, 1, 1)).toBeNull()
  expect(imagePoint(NaN, 1, 1, 1, 1, 1)).toBeNull()
})
