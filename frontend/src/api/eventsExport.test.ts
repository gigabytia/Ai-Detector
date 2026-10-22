import { afterEach, expect, it, vi } from 'vitest'
import { eventParams, exportEvents, fetchEvents } from './events'
const fetchMock = vi.fn()
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
})
it('shares exactly the list/export camera status type and UTC period filters', async () => {
  vi.stubGlobal(
    'fetch',
    fetchMock.mockResolvedValue(new Response('{"items":[],"next_cursor":null}', { status: 200 })),
  )
  const filters = {
    cameraId: 'camera',
    status: 'FALSE_POSITIVE',
    eventType: 'PERSON_LOITERING_IN_DANGER_ZONE',
    start: '2026-01-01T00:00:00Z',
    end: '2026-01-02T00:00:00Z',
  }
  await fetchEvents('cursor', filters.cameraId, filters.status, undefined, filters)
  const url = new URL(fetchMock.mock.calls.at(-1)![0], 'http://test')
  for (const [key, value] of eventParams(filters)) expect(url.searchParams.get(key)).toBe(value)
  expect(url.searchParams.get('cursor')).toBe('cursor')
  expect(url.searchParams.get('limit')).toBe('50')
})
it('downloads a blob and removes anchor/revokes URL', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', fetchMock.mockResolvedValue(new Response('id\r\n1', { status: 200 })))
  const create = vi.fn(() => 'blob:qa'),
    revoke = vi.fn()
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }))
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  await exportEvents({ cameraId: 'camera' })
  expect(click).toHaveBeenCalledOnce()
  expect(create).toHaveBeenCalledOnce()
  expect(document.querySelector('a[download]')).toBeNull()
  await vi.runAllTimersAsync()
  expect(revoke).toHaveBeenCalledWith('blob:qa')
})
it('rejects JSON export errors rather than downloading an error file', async () => {
  vi.stubGlobal(
    'fetch',
    fetchMock.mockResolvedValue(
      new Response('{"error":{"code":"EXPORT_TOO_LARGE","message":"narrow"}}', { status: 422 }),
    ),
  )
  await expect(exportEvents({})).rejects.toMatchObject({ code: 'EXPORT_TOO_LARGE', status: 422 })
})
