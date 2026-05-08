import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, reportsApi } from '@/services/api'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('reportsApi', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('builds the URL with include_risks=true', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }))

    await reportsApi.getRiskSummary('2026-01-01', '2026-02-01', true)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/reports/risk-summary?start=2026-01-01&end=2026-02-01&include_risks=true')
  })

  it('builds the URL with include_risks=false', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }))

    await reportsApi.getRiskSummary('2026-03-15', '2026-04-15', false)

    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/reports/risk-summary?start=2026-03-15&end=2026-04-15&include_risks=false')
  })

  it('returns the parsed body on success', async () => {
    const payload = {
      generated_at: '2026-05-08T12:00:00Z',
      generated_by: { id: 1, email: 'a@b.com', full_name: null, role: 'admin' },
      date_range: { start: '2026-01-01', end: '2026-02-01' },
      summary: { total: 0, by_status: {}, by_severity: {}, overdue_treatments: 0, overdue_reviews: 0, risk_matrix: [] },
      score_history: { points: [] },
      risks: null,
    }
    fetchMock.mockResolvedValueOnce(jsonResponse(payload))

    const result = await reportsApi.getRiskSummary('2026-01-01', '2026-02-01', false)

    expect(result).toEqual(payload)
  })

  it('propagates an ApiError on a 403 response', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'Forbidden' }, 403))

    let thrown: unknown
    try {
      await reportsApi.getRiskSummary('2026-01-01', '2026-02-01', true)
    } catch (err) {
      thrown = err
    }

    expect(thrown).toBeInstanceOf(ApiError)
    expect((thrown as ApiError).status).toBe(403)
    expect((thrown as ApiError).message).toBe('Forbidden')
  })
})
