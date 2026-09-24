import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { risksApi } from '@/services/api'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function page(ids: number[], total: number) {
  return { total, items: ids.map((id) => ({ id, risk_id: `RISK-${id}` })) }
}

/** [start, end) */
function range(start: number, end: number): number[] {
  return Array.from({ length: end - start }, (_, i) => start + i)
}

describe('risksApi.listAll', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('pages through the whole register instead of stopping at the first page', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(page(range(1, 201), 450)))
      .mockResolvedValueOnce(jsonResponse(page(range(201, 401), 450)))
      .mockResolvedValueOnce(jsonResponse(page(range(401, 451), 450)))

    const result = await risksApi.listAll()

    expect(result.total).toBe(450)
    expect(result.items.map((r) => r.id)).toEqual(range(1, 451))
    expect(fetchMock.mock.calls.map(([url]) => url as string)).toEqual([
      '/api/risks?skip=0&limit=200',
      '/api/risks?skip=200&limit=200',
      '/api/risks?skip=400&limit=200',
    ])
  })

  it('makes one request, keeping filters, when everything fits on a page', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(page([1, 2, 3], 3)))

    const result = await risksApi.listAll({ due_for_review: true })

    expect(result.items).toHaveLength(3)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/risks?due_for_review=true&skip=0&limit=200')
  })

  it('skips a risk repeated across pages when the register shifts mid-fetch', async () => {
    // A risk created between the two requests pushes #200 onto page two as well.
    fetchMock
      .mockResolvedValueOnce(jsonResponse(page(range(1, 201), 201)))
      .mockResolvedValueOnce(jsonResponse(page([200, 201], 202)))

    const result = await risksApi.listAll()

    expect(result.items.map((r) => r.id)).toEqual(range(1, 202))
  })
})
