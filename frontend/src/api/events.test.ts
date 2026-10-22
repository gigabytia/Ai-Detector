import { afterEach, expect, it, vi } from 'vitest'
import { updateEvent } from './events'
import { apiRequest, ApiError } from './http'
vi.mock('./http', async (original) => ({
  ...(await original<typeof import('./http')>()),
  apiRequest: vi.fn(),
}))
afterEach(() => {
  vi.resetAllMocks()
  vi.useRealTimers()
})
it('retries the exact not-persisted error then saves once', async () => {
  vi.useFakeTimers()
  vi.mocked(apiRequest)
    .mockRejectedValueOnce(new ApiError(409, 'EVENT_NOT_PERSISTED_YET', 'pending'))
    .mockResolvedValueOnce({ id: 'a' })
  const pending = updateEvent('a', { status: 'ACKNOWLEDGED' })
  await vi.advanceTimersByTimeAsync(500)
  expect(await pending).toEqual({ id: 'a' })
  expect(apiRequest).toHaveBeenCalledTimes(2)
})
it('does not retry a final status conflict', async () => {
  vi.mocked(apiRequest).mockRejectedValueOnce(new ApiError(409, 'EVENT_STATUS_CONFLICT', 'final'))
  await expect(updateEvent('a', { status: 'FALSE_POSITIVE' })).rejects.toThrow('final')
  expect(apiRequest).toHaveBeenCalledTimes(1)
})
