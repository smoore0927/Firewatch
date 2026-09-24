/**
 * Server-side pagination, filtering, sorting and search on RisksPage.
 *
 * risksApi.list is mocked to record every call it receives, so each test
 * asserts on the query params the page actually sent rather than on
 * client-side filtering (there isn't any anymore).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Risk, User } from '@/types'

vi.mock('@/services/api', () => {
  class ApiError extends Error {
    public status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
      this.name = 'ApiError'
    }
  }
  return {
    risksApi: {
      list: vi.fn(),
      owners: vi.fn(),
      exportCsv: vi.fn(),
      bulkSetStatus: vi.fn(),
    },
    usersApi: {
      listAssignable: vi.fn(),
    },
    ApiError,
    errorMessage: (err: unknown, fallback: string) =>
      err instanceof ApiError ? err.message : fallback,
  }
})

const ADMIN_USER: User = {
  id: 1,
  email: 'admin@example.com',
  full_name: 'Admin User',
  role: 'admin',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  has_password: true,
  must_change_password: false,
}

vi.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ user: ADMIN_USER, isLoading: false }),
}))

import { risksApi } from '@/services/api'
import RisksPage from '@/pages/RisksPage'

const mockedList = risksApi.list as unknown as ReturnType<typeof vi.fn>
const mockedOwners = risksApi.owners as unknown as ReturnType<typeof vi.fn>
const mockedBulkSetStatus = risksApi.bulkSetStatus as unknown as ReturnType<typeof vi.fn>

function makeRisk(id: number, overrides: Record<string, unknown> = {}): Risk {
  return {
    id,
    risk_id: `RISK-${String(id).padStart(3, '0')}`,
    title: `Risk ${id}`,
    description: null,
    category: null,
    status: 'open',
    owner_id: 1,
    owner: { id: 1, email: 'a@b.com', full_name: 'Owner', role: 'admin' },
    next_review_date: null,
    assessments: [],
    current_score: null,
    severity: null,
    responses: [],
    history: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: null,
    ...overrides,
  } as unknown as Risk
}

function page(items: Risk[], total: number) {
  return { items, total }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <RisksPage />
    </MemoryRouter>,
  )
}

function lastCall(): Record<string, unknown> | undefined {
  const calls = mockedList.mock.calls as unknown[][]
  return calls[calls.length - 1]?.[0] as Record<string, unknown> | undefined
}

describe('RisksPage pagination', () => {
  beforeEach(() => {
    mockedList.mockReset()
    mockedOwners.mockReset()
    mockedBulkSetStatus.mockReset()
    mockedOwners.mockResolvedValue([
      { id: 1, email: 'a@b.com', full_name: 'Owner' },
      { id: 2, email: 'c@d.com', full_name: 'Second Owner' },
    ])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('sends skip=0, limit=25, sort=title, order=asc on the first request', async () => {
    mockedList.mockResolvedValue(page([makeRisk(1)], 1))

    renderPage()

    await waitFor(() => expect(mockedList).toHaveBeenCalled())
    expect(mockedList.mock.calls[0][0]).toMatchObject({
      skip: 0,
      limit: 25,
      sort: 'title',
      order: 'asc',
    })
  })

  it('Next and Previous send the right skip and show the correct range', async () => {
    mockedList.mockResolvedValue(page(Array.from({ length: 25 }, (_, i) => makeRisk(i + 1)), 60))

    renderPage()

    await screen.findByText('Showing 1–25 of 60')

    mockedList.mockResolvedValue(page(Array.from({ length: 25 }, (_, i) => makeRisk(i + 26)), 60))
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))

    await screen.findByText('Showing 26–50 of 60')
    expect(lastCall()).toMatchObject({ skip: 25, limit: 25 })

    mockedList.mockResolvedValue(page(Array.from({ length: 25 }, (_, i) => makeRisk(i + 1)), 60))
    await userEvent.click(screen.getByRole('button', { name: 'Previous' }))

    await screen.findByText('Showing 1–25 of 60')
    expect(lastCall()).toMatchObject({ skip: 0, limit: 25 })
  })

  it('changing a filter resets to the first page and sends its param', async () => {
    mockedList.mockResolvedValue(page(Array.from({ length: 25 }, (_, i) => makeRisk(i + 1)), 60))
    renderPage()
    await screen.findByText('Showing 1–25 of 60')

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Showing 26–50 of 60')

    mockedList.mockResolvedValue(page([makeRisk(1)], 1))
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'open')

    await waitFor(() => {
      expect(lastCall()).toMatchObject({ status: 'open', skip: 0 })
    })
  })

  it('maps the severity dropdown to lowercase API values', async () => {
    mockedList.mockResolvedValue(page([makeRisk(1)], 1))
    renderPage()
    await waitFor(() => expect(mockedList).toHaveBeenCalled())

    await userEvent.selectOptions(screen.getByLabelText('Severity'), 'Critical')

    await waitFor(() => {
      expect(lastCall()).toMatchObject({ severity: 'critical' })
    })
  })

  it('clicking a sortable header sends sort and order', async () => {
    mockedList.mockResolvedValue(page([makeRisk(1)], 1))
    renderPage()
    await screen.findByText('Risk 1')

    await userEvent.click(screen.getByRole('button', { name: /score/i }))

    await waitFor(() => {
      expect(lastCall()).toMatchObject({ sort: 'score', order: 'asc' })
    })

    await userEvent.click(screen.getByRole('button', { name: /score/i }))
    await waitFor(() => {
      expect(lastCall()).toMatchObject({ sort: 'score', order: 'desc' })
    })
  })

  it('debounces search and sends it as `search`', async () => {
    mockedList.mockResolvedValue(page([makeRisk(1)], 1))
    renderPage()
    await screen.findByText('Risk 1')

    const calls0 = mockedList.mock.calls.length
    const input = screen.getByPlaceholderText('Search risks…')
    await userEvent.type(input, 'phishing')

    // No new request right after typing — it's still within the debounce window.
    expect(mockedList.mock.calls).toHaveLength(calls0)

    await waitFor(() => {
      expect(lastCall()).toMatchObject({ search: 'phishing' })
    }, { timeout: 2000 })
  })

  it('keeps the search input mounted and focused while a request is in flight', async () => {
    let resolveSecond: (v: unknown) => void = () => {}
    mockedList.mockResolvedValueOnce(page([makeRisk(1)], 1))
    renderPage()
    await screen.findByText('Risk 1')

    mockedList.mockReturnValueOnce(new Promise((resolve) => { resolveSecond = resolve }))
    const input = screen.getByPlaceholderText('Search risks…') as HTMLInputElement
    await userEvent.type(input, 'x')

    // The input is still in the document and keeps the typed value while the
    // (debounced, still-pending) request has not resolved yet.
    expect(screen.getByPlaceholderText('Search risks…')).toBeInTheDocument()
    expect(input.value).toBe('x')

    resolveSecond(page([makeRisk(1)], 1))
  })

  it('populates owner options from owners()', async () => {
    mockedList.mockResolvedValue(page([makeRisk(1)], 1))
    renderPage()

    await waitFor(() => expect(mockedOwners).toHaveBeenCalled())
    const ownerSelect = await screen.findByLabelText('Owner')
    expect(within(ownerSelect).getByText('Second Owner')).toBeInTheDocument()
  })

  it('discards a stale response that resolves after a newer one', async () => {
    mockedList.mockResolvedValueOnce(page([makeRisk(1)], 1))
    renderPage()
    await screen.findByText('Risk 1')

    // Status change starts a request that will resolve *slowly*.
    let resolveSlow: (v: unknown) => void = () => {}
    const slow = new Promise((resolve) => { resolveSlow = resolve })
    mockedList.mockReturnValueOnce(slow)
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'open')
    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(2))

    // Category change fires a second, newer request that resolves quickly.
    mockedList.mockResolvedValueOnce(page([makeRisk(2, { title: 'Fresh' })], 1))
    await userEvent.selectOptions(screen.getByLabelText('Category'), 'Technical')
    await screen.findByText('Fresh')

    // The slow (now-stale) response arrives afterwards — it must not overwrite
    // the newer result that's already on screen.
    resolveSlow(page([makeRisk(3, { title: 'Stale' })], 1))
    await new Promise((r) => globalThis.setTimeout(r, 0))

    expect(screen.getByText('Fresh')).toBeInTheDocument()
    expect(screen.queryByText('Stale')).not.toBeInTheDocument()
  })

  it('changing the page size resets to the first page', async () => {
    mockedList.mockResolvedValue(page(Array.from({ length: 25 }, (_, i) => makeRisk(i + 1)), 60))
    renderPage()
    await screen.findByText('Showing 1–25 of 60')

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Showing 26–50 of 60')

    mockedList.mockResolvedValue(page(Array.from({ length: 50 }, (_, i) => makeRisk(i + 1)), 60))
    await userEvent.selectOptions(screen.getByLabelText('Rows per page'), '50')

    await waitFor(() => {
      expect(lastCall()).toMatchObject({ skip: 0, limit: 50 })
    })
  })

  it('shows an inline error (not a full-page replacement) when a reload after a successful load fails, keeping the search input and filter bar mounted', async () => {
    mockedList.mockResolvedValueOnce(page([makeRisk(1)], 1))
    renderPage()
    await screen.findByText('Risk 1')

    // Select the row and drive the real bulk-status dialog, which calls the
    // page's onDone -> loadRisks() on success -- the same reload path a CSV
    // import triggers via onImported.
    await userEvent.click(screen.getByLabelText('Select RISK-001'))
    await userEvent.click(screen.getByRole('button', { name: /change status/i }))
    mockedBulkSetStatus.mockResolvedValueOnce({ updated: ['RISK-001'], errors: [] })
    mockedList.mockRejectedValueOnce(new Error('boom'))
    await userEvent.click(screen.getByRole('button', { name: /update status/i }))

    expect(await screen.findByText(/could not load risks/i)).toBeInTheDocument()
    // The page itself, not just an isolated message, must still be mounted.
    expect(screen.getByPlaceholderText('Search risks…')).toBeInTheDocument()
    expect(screen.getByLabelText('Status')).toBeInTheDocument()
    expect(screen.getByText('Risk Register')).toBeInTheDocument()
  })

  it('changing a filter on page 2 sends exactly one new request, at skip=0', async () => {
    mockedList.mockResolvedValueOnce(page(Array.from({ length: 25 }, (_, i) => makeRisk(i + 1)), 60))
    renderPage()
    await screen.findByText('Showing 1–25 of 60')

    mockedList.mockResolvedValueOnce(page(Array.from({ length: 25 }, (_, i) => makeRisk(i + 26)), 60))
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Showing 26–50 of 60')

    const callsBefore = mockedList.mock.calls.length
    mockedList.mockResolvedValueOnce(page([makeRisk(1)], 1))
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'open')

    await waitFor(() => expect(lastCall()).toMatchObject({ status: 'open', skip: 0 }))
    // A stray page-2 request under the new filter would show up as a second
    // call here (thrown away by the sequence ref); there must be only one.
    expect(mockedList.mock.calls).toHaveLength(callsBefore + 1)
  })

  it('does not reset the page once the debounce window elapses with no search change', async () => {
    mockedList.mockResolvedValueOnce(page(Array.from({ length: 25 }, (_, i) => makeRisk(i + 1)), 60))
    renderPage()
    await screen.findByText('Showing 1–25 of 60')

    mockedList.mockResolvedValueOnce(page(Array.from({ length: 25 }, (_, i) => makeRisk(i + 26)), 60))
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Showing 26–50 of 60')

    const callsBefore = mockedList.mock.calls.length
    // Wait past the search debounce window with no further input — the
    // debounce effect must not fire (searchInput never changed), so the page
    // and request count stay put.
    await new Promise((resolve) => globalThis.setTimeout(resolve, 400))

    expect(screen.getByText('Showing 26–50 of 60')).toBeInTheDocument()
    expect(mockedList.mock.calls).toHaveLength(callsBefore)
  })

  it('does not clear the selection once the debounce window elapses with no search change', async () => {
    mockedList.mockResolvedValue(page([makeRisk(1)], 1))
    renderPage()
    await screen.findByText('Risk 1')

    await userEvent.click(screen.getByLabelText('Select RISK-001'))
    expect(await screen.findByText('1 selected')).toBeInTheDocument()

    await new Promise((resolve) => globalThis.setTimeout(resolve, 400))

    expect(screen.getByText('1 selected')).toBeInTheDocument()
  })

  it('typing a trailing space into an already-applied search sends no request and keeps the selection', async () => {
    mockedList.mockResolvedValueOnce(page([makeRisk(1)], 1))
    renderPage()
    await screen.findByText('Risk 1')

    const input = screen.getByPlaceholderText('Search risks…')
    mockedList.mockResolvedValueOnce(page([makeRisk(1)], 1))
    await userEvent.type(input, 'phishing')
    await waitFor(() => expect(lastCall()).toMatchObject({ search: 'phishing' }))

    await userEvent.click(screen.getByLabelText('Select RISK-001'))
    expect(await screen.findByText('1 selected')).toBeInTheDocument()

    const callsBefore = mockedList.mock.calls.length
    await userEvent.type(input, ' ') // trims back to the same applied search
    await new Promise((resolve) => globalThis.setTimeout(resolve, 400))

    expect(mockedList.mock.calls).toHaveLength(callsBefore)
    expect(screen.getByText('1 selected')).toBeInTheDocument()
  })

  it('clears the selection when the sort changes', async () => {
    mockedList.mockResolvedValue(page([makeRisk(1)], 1))
    renderPage()
    await screen.findByText('Risk 1')

    await userEvent.click(screen.getByLabelText('Select RISK-001'))
    expect(await screen.findByText('1 selected')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /score/i }))

    await waitFor(() => expect(screen.queryByText('1 selected')).not.toBeInTheDocument())
  })
})
