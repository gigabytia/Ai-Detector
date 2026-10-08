import { ApiError } from '@/api/http'

const KNOWN_CODES = new Set([
  'CAMERA_NOT_FOUND',
  'CAMERA_ALREADY_EXISTS',
  'CAMERA_LIMIT_REACHED',
  'INVALID_CAMERA_SOURCE',
  'UPLOAD_REJECTED',
  'UPLOAD_TOO_LARGE',
  'VALIDATION_ERROR',
])

/** i18n key for an error shown to the operator; never the raw server text (§120). */
export function errorMessageKey(error: unknown): string {
  if (error instanceof ApiError && KNOWN_CODES.has(error.code)) {
    return `errors.${error.code}`
  }
  if (error instanceof ApiError && error.status >= 500) {
    return 'errors.server'
  }
  return error instanceof ApiError ? 'errors.unknown' : 'errors.network'
}
