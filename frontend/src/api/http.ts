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

type Method = 'GET' | 'POST' | 'PATCH' | 'DELETE'

/**
 * Call the API. A plain object body is sent as JSON, FormData as multipart.
 * Non-2xx responses become ApiError with the backend error code; 204 resolves to undefined.
 */
export async function apiRequest<T>(
  method: Method,
  path: string,
  options: { body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  let body: BodyInit | undefined
  if (options.body instanceof FormData) {
    body = options.body
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  const response = await fetch(path, { method, headers, body, signal: options.signal })
  const data: unknown =
    response.status === 204 ? undefined : await response.json().catch(() => null)
  if (!response.ok) {
    if (isErrorResponse(data)) {
      throw new ApiError(response.status, data.error.code, data.error.message)
    }
    throw new ApiError(response.status, 'HTTP_ERROR', response.statusText)
  }
  return data as T
}

export function apiGet<T>(path: string, init?: { signal?: AbortSignal | null }): Promise<T> {
  return apiRequest<T>('GET', path, { signal: init?.signal ?? undefined })
}
