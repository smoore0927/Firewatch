/**
 * Tests for the audit API client.
 *
 * The api module is exercised by stubbing the global fetch with a Vitest mock
 * so we can assert the exact URL/method that hits the wire and inspect the
 * shape of any thrown errors.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, auditApi } from '@/services/api'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('auditApi', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('listActions hits GET /api/audit/actions and returns the parsed body', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ actions: ['risk.create', 'auth.login'] }))

    const result = await auditApi.listActions()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/audit/actions')
    // request<T> uses fetch's default GET when no method is provided.
    expect(init?.method).toBeUndefined()
    expect(result).toEqual({ actions: ['risk.create', 'auth.login'] })
  })

  it('list with no params hits GET /api/audit/logs with no query string', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ total: 0, items: [] }))

    await auditApi.list()

    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/audit/logs')
  })

  it('list with action filter encodes the action correctly', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ total: 0, items: [] }))

    await auditApi.list({ action: 'risk.create' })

    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/audit/logs?action=risk.create')
  })

  it('list with skip + limit appends both query params', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ total: 0, items: [] }))

    await auditApi.list({ skip: 100, limit: 50 })

    const [url] = fetchMock.mock.calls[0]
    expect(url).toContain('skip=100')
    expect(url).toContain('limit=50')
  })

  it('list with start + end appends both as ISO strings', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ total: 0, items: [] }))

    const start = '2026-01-01T00:00:00.000Z'
    const end = '2026-01-08T00:00:00.000Z'
    await auditApi.list({ start, end })

    const [url] = fetchMock.mock.calls[0] as [string]
    // URLSearchParams URL-encodes the colons in ISO timestamps.
    expect(url).toContain(`start=${encodeURIComponent(start)}`)
    expect(url).toContain(`end=${encodeURIComponent(end)}`)
  })

  it('list propagates an ApiError on a 403 response', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'Forbidden' }, 403))

    let thrown: unknown
    try {
      await auditApi.list()
    } catch (err) {
      thrown = err
    }

    expect(thrown).toBeInstanceOf(ApiError)
    expect((thrown as ApiError).status).toBe(403)
    expect((thrown as ApiError).message).toBe('Forbidden')
  })
})
