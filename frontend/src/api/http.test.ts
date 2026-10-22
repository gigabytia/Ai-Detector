import { afterEach, expect, it, vi } from 'vitest'
import { apiGet, ApiError } from './http'

afterEach(() => vi.unstubAllGlobals())

it.each([null, { error: null }, { error: {} }, { error: { code: 1, message: [] } }])(
  'handles a malformed upstream error envelope: %j',
  async (body) => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify(body), { status: 502, statusText: 'Bad Gateway' }),
        ),
    )
    await expect(apiGet('/api/v1/cameras')).rejects.toMatchObject({
      name: 'ApiError',
      status: 502,
      code: 'HTTP_ERROR',
    } satisfies Partial<ApiError>)
  },
)
