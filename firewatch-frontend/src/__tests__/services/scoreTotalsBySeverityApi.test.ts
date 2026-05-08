import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, dashboardApi } from '@/services/api'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('dashboardApi.getScoreTotalsBySeverity', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('builds the URL with the start and end query params', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ points: [] }))

    await dashboardApi.getScoreTotalsBySeverity('2026-01-01', '2026-02-01')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/dashboard/score-totals-by-severity?start=2026-01-01&end=2026-02-01')
    // request<T> uses fetch's default GET when no method is provided.
    expect(init?.method).toBeUndefined()
  })

  it('returns the parsed body on success', async () => {
    const payload = {
      points: [
        { date: '2026-01-05', low: 4, medium: 18, high: 0, critical: 25 },
        { date: '2026-01-06', low: 0, medium: 12, high: 16, critical: 0 },
      ],
    }
    fetchMock.mockResolvedValueOnce(jsonResponse(payload))

    const result = await dashboardApi.getScoreTotalsBySeverity('2026-01-01', '2026-02-01')

    expect(result).toEqual(payload)
  })

  it('propagates an ApiError on a 403 response', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'Forbidden' }, 403))

    let thrown: unknown
    try {
      await dashboardApi.getScoreTotalsBySeverity('2026-01-01', '2026-02-01')
    } catch (err) {
      thrown = err
    }

    expect(thrown).toBeInstanceOf(ApiError)
    expect((thrown as ApiError).status).toBe(403)
    expect((thrown as ApiError).message).toBe('Forbidden')
  })
})
