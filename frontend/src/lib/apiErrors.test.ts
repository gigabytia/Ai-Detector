import { describe, expect, it } from 'vitest'

import { ApiError } from '@/api/http'

import { errorMessageKey } from './apiErrors'

describe('errorMessageKey', () => {
  it('maps known backend codes and generic failures', () => {
    expect(errorMessageKey(new ApiError(409, 'CAMERA_ALREADY_EXISTS', 'x'))).toBe(
      'errors.CAMERA_ALREADY_EXISTS',
    )
    expect(errorMessageKey(new ApiError(500, 'INTERNAL_ERROR', 'x'))).toBe('errors.server')
    expect(errorMessageKey(new ApiError(400, 'SOMETHING', 'x'))).toBe('errors.unknown')
    expect(errorMessageKey(new TypeError('Failed to fetch'))).toBe('errors.network')
  })
})
