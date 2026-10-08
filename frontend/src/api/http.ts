import type { components } from './generated'

type ErrorResponse = components['schemas']['ErrorResponse']

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as { error: unknown }).error === 'object'
  )
}

/** GET a JSON resource. Non-2xx responses become ApiError with the backend error code. */
export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { Accept: 'application/json' } })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    if (isErrorResponse(body)) {
      throw new ApiError(response.status, body.error.code, body.error.message)
    }
    throw new ApiError(response.status, 'HTTP_ERROR', response.statusText)
  }
  return body as T
}
