/**
 * RisksPage keeps its view (filters, search, sort, page) in the URL, so a
 * refresh, a shared link, or coming back from a risk lands on the same page.
 * Also covers the Page dropdown.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
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
import { registerPath } from '@/lib/register-view'
import RisksPage from '@/pages/RisksPage'

const mockedList = risksApi.list as unknown as ReturnType<typeof vi.fn>
const mockedOwners = risksApi.owners as unknown as ReturnType<typeof vi.fn>

// Covers the 300 ms search debounce plus a render under a loaded test run.
const SETTLE = { timeout: 3000 }

function makeRisk(id: number): Risk {
  return {
    id,
    risk_id: `RISK-${String(id).padStart(3, '0')}`,
    title: `Risk ${id}`,
    description: null,
    category: null,
    status: 'open',
    owner_id: 1,
    owner: { id: 1, email: 'a@b.com', full_name: 'Owner' },
    next_review_date: null,
    assessments: [],
    current_score: null,
    severity: null,
    responses: [],
    history: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: null,
  } as unknown as Risk
}

// A 60-risk register served in pages, honouring skip/limit like the API.
function serveRegister(total = 60) {
  vi.mocked(risksApi.list).mockImplementation((params) => {
    const skip = params?.skip ?? 0
    const limit = params?.limit ?? 25
    const count = Math.max(0, Math.min(limit, total - skip))
    return Promise.resolve({ items: Array.from({ length: count }, (_, i) => makeRisk(skip + i + 1)), total })
  })
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.search}</output>
}

function DetailStub() {
  const navigate = useNavigate()
  return (
    <div>
      <p>Risk detail</p>
      <button type="button" onClick={() => { void navigate(-1) }}>Browser back</button>
      <button type="button" onClick={() => navigate(registerPath())}>Back to register</button>
    </div>
  )
}

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route
          path="/risks"
          element={
            <>
              <RisksPage />
              <LocationProbe />
              <Link to="/risks">Sidebar risks link</Link>
            </>
          }
        />
        <Route path="/risks/:riskId" element={<DetailStub />} />
      </Routes>
    </MemoryRouter>,
  )
}

function urlParams(): URLSearchParams {
  return new URLSearchParams(screen.getByTestId('location').textContent ?? '')
}

function lastCall(): Record<string, unknown> | undefined {
  const calls = mockedList.mock.calls as unknown[][]
  return calls[calls.length - 1]?.[0] as Record<string, unknown> | undefined
}

describe('RisksPage URL state', () => {
  beforeEach(() => {
    mockedList.mockReset()
    mockedOwners.mockReset()
    mockedOwners.mockResolvedValue([
      { id: 1, email: 'a@b.com', full_name: 'Owner' },
      { id: 2, email: 'c@d.com', full_name: 'Second Owner' },
    ])
    sessionStorage.clear()
  })

  it('loads the view described by the URL and shows it in the controls', async () => {
    serveRegister(400)
    renderAt('/risks?page=3&size=50&q=phish&status=open&category=Technical&owner=2&severity=high&due=1&sort=score&order=desc')

    await screen.findByText('Showing 101–150 of 400')
    expect(mockedList.mock.calls[0][0]).toMatchObject({
      skip: 100,
      limit: 50,
      search: 'phish',
      status: 'open',
      category: 'Technical',
      owner_id: 2,
      severity: 'high',
      due_for_review: true,
      sort: 'score',
      order: 'desc',
    })
    expect(screen.getByPlaceholderText('Search risks…')).toHaveValue('phish')
    expect(screen.getByLabelText('Status')).toHaveValue('open')
    expect(screen.getByLabelText('Severity')).toHaveValue('high')
    expect(screen.getByLabelText('Due for review only')).toBeChecked()
    expect(screen.getByLabelText('Rows per page')).toHaveValue('50')
    expect(screen.getByLabelText('Page')).toHaveValue('3')
  })

  it('falls back to defaults for invalid params', async () => {
    serveRegister()
    renderAt('/risks?page=abc&size=7&sort=bogus&severity=extreme&status=nope')

    await screen.findByText('Showing 1–25 of 60')
    expect(mockedList.mock.calls[0][0]).toMatchObject({ skip: 0, limit: 25, sort: 'title', order: 'asc' })
    expect(mockedList.mock.calls[0][0]).not.toHaveProperty('severity', expect.anything())
    expect(mockedList.mock.calls[0][0]).not.toHaveProperty('status', expect.anything())
  })

  it('writes filter, sort and page changes to the URL', async () => {
    serveRegister()
    renderAt('/risks')
    await screen.findByText('Showing 1–25 of 60')
    expect(urlParams().toString()).toBe('')

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Showing 26–50 of 60')
    expect(urlParams().get('page')).toBe('2')

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'open')
    await waitFor(() => expect(urlParams().get('status')).toBe('open'))
    expect(urlParams().get('page')).toBeNull() // a filter change goes back to page 1

    await userEvent.click(screen.getByRole('button', { name: /Score/ }))
    await waitFor(() => expect(urlParams().get('sort')).toBe('score'))

    await userEvent.type(screen.getByPlaceholderText('Search risks…'), 'phish')
    await waitFor(() => expect(urlParams().get('q')).toBe('phish'), SETTLE)
    expect(lastCall()).toMatchObject({ search: 'phish', status: 'open', sort: 'score' })
  })

  it('comes back to the same page after opening a risk and pressing Back', async () => {
    serveRegister()
    renderAt('/risks')
    await screen.findByText('Showing 1–25 of 60')
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Showing 26–50 of 60')

    await userEvent.click(screen.getByText('Risk 26'))
    await screen.findByText('Risk detail')
    await userEvent.click(screen.getByRole('button', { name: 'Browser back' }))

    await screen.findByText('Showing 26–50 of 60')
    expect(lastCall()).toMatchObject({ skip: 25 })
  })

  it("comes back to the same view through the detail page's register link", async () => {
    serveRegister()
    renderAt('/risks')
    await screen.findByText('Showing 1–25 of 60')
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'open')
    await waitFor(() => expect(urlParams().get('status')).toBe('open'))
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Showing 26–50 of 60')

    await userEvent.click(screen.getByText('Risk 26'))
    await screen.findByText('Risk detail')
    await userEvent.click(screen.getByRole('button', { name: 'Back to register' }))

    await screen.findByText('Showing 26–50 of 60')
    expect(lastCall()).toMatchObject({ skip: 25, status: 'open' })
    expect(screen.getByLabelText('Status')).toHaveValue('open')
  })

  it('jumps to a page picked from the Page dropdown', async () => {
    serveRegister()
    renderAt('/risks')
    await screen.findByText('Showing 1–25 of 60')
    expect(screen.getByText('of 3')).toBeInTheDocument()

    const pagePicker = screen.getByLabelText('Page')
    expect(within(pagePicker).getAllByRole('option').map((o) => o.textContent)).toEqual(['1', '2', '3'])

    await userEvent.selectOptions(pagePicker, '3')

    await screen.findByText('Showing 51–60 of 60')
    expect(lastCall()).toMatchObject({ skip: 50 })
    expect(urlParams().get('page')).toBe('3')
  })

  it('keeps the Page dropdown in step with Next and Previous', async () => {
    serveRegister()
    renderAt('/risks')
    await screen.findByText('Showing 1–25 of 60')

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Showing 26–50 of 60')
    expect(screen.getByLabelText('Page')).toHaveValue('2')

    await userEvent.click(screen.getByRole('button', { name: 'Previous' }))
    await screen.findByText('Showing 1–25 of 60')
    expect(screen.getByLabelText('Page')).toHaveValue('1')
  })

  it('offers one page per page-size chunk', async () => {
    serveRegister()
    renderAt('/risks')
    await screen.findByText('Showing 1–25 of 60')

    await userEvent.selectOptions(screen.getByLabelText('Rows per page'), '50')

    await screen.findByText('Showing 1–50 of 60')
    expect(within(screen.getByLabelText('Page')).getAllByRole('option')).toHaveLength(2)
    expect(screen.getByText('of 2')).toBeInTheDocument()
  })

  it('steps back to the last page when the URL points past the end', async () => {
    serveRegister()
    renderAt('/risks?page=9')

    await screen.findByText('Showing 51–60 of 60')
    expect(urlParams().get('page')).toBe('3')
  })

  it('resets the search box, filters and selection when the URL changes from outside the page', async () => {
    serveRegister()
    renderAt('/risks?q=phish&status=open')
    await screen.findByText('Showing 1–25 of 60')
    await userEvent.click(screen.getByLabelText('Select RISK-001'))
    expect(screen.getByText('1 selected')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('link', { name: 'Sidebar risks link' }))

    await waitFor(() => expect(screen.getByPlaceholderText('Search risks…')).toHaveValue(''))
    expect(screen.getByLabelText('Status')).toHaveValue('all')
    expect(screen.queryByText('1 selected')).not.toBeInTheDocument()
    await waitFor(() => expect(lastCall()).not.toHaveProperty('search', expect.anything()))
  })

  it('keeps half-typed search text when a filter changes, then applies both', async () => {
    serveRegister()
    renderAt('/risks')
    await screen.findByText('Showing 1–25 of 60')

    await userEvent.type(screen.getByPlaceholderText('Search risks…'), 'phish')
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'open')

    expect(screen.getByPlaceholderText('Search risks…')).toHaveValue('phish')
    await waitFor(() => expect(lastCall()).toMatchObject({ search: 'phish', status: 'open' }), SETTLE)
    expect(urlParams().get('q')).toBe('phish')
    expect(urlParams().get('status')).toBe('open')
  })
})
