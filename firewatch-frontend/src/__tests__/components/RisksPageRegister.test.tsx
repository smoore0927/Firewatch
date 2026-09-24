/**
 * RisksPage register rendering: every risk is listed, and review dates show on
 * their own calendar day with the overdue flag keyed to the local date.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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
      listAll: vi.fn(),
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
import RisksPage from '@/pages/RisksPage'

const mockedListAll = risksApi.listAll as unknown as ReturnType<typeof vi.fn>

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

function renderPage() {
  return render(
    <MemoryRouter>
      <RisksPage />
    </MemoryRouter>,
  )
}

describe('RisksPage register', () => {
  beforeEach(() => {
    mockedListAll.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('lists every risk, not just the first page', async () => {
    const risks = Array.from({ length: 60 }, (_, i) => makeRisk(i + 1))
    mockedListAll.mockResolvedValue({ items: risks, total: 60 })

    renderPage()

    await screen.findByText('Risk 60')
    expect(screen.getByText('60 risks total')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(61) // header + 60
  })

  it('shows review dates on their calendar day and flags only those due by local today', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 8, 22, 21, 30)) // a US evening: already Sep 23 in UTC
    mockedListAll.mockResolvedValue({
      items: [
        makeRisk(1, { next_review_date: '2026-09-22' }),
        makeRisk(2, { next_review_date: '2026-09-23' }),
      ],
      total: 2,
    })

    renderPage()

    const dueToday = await screen.findByText(new Date(2026, 8, 22).toLocaleDateString())
    const dueTomorrow = screen.getByText(new Date(2026, 8, 23).toLocaleDateString())
    expect(dueToday.className).toContain('bg-red-100')
    expect(dueTomorrow.className).not.toContain('bg-red-100')
  })
})
