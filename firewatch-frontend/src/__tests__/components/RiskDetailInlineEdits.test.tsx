/**
 * RiskDetailPage inline edits (status, log review) surface failures instead of
 * silently snapping back, and dates render on their own calendar day.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
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
      get: vi.fn(),
      update: vi.fn(),
      addAssessment: vi.fn(),
    },
    usersApi: {
      listAssignable: vi.fn().mockResolvedValue([]),
    },
    frameworksApi: {
      getFrameworks: vi.fn().mockResolvedValue([]),
      getRiskControls: vi.fn().mockResolvedValue([]),
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

import { ApiError, risksApi } from '@/services/api'
import { rememberRegisterSearch } from '@/lib/register-view'
import RiskDetailPage from '@/pages/RiskDetailPage'

const mockedGet = risksApi.get as unknown as ReturnType<typeof vi.fn>
const mockedUpdate = risksApi.update as unknown as ReturnType<typeof vi.fn>
const mockedAddAssessment = risksApi.addAssessment as unknown as ReturnType<typeof vi.fn>

function makeRisk(): Risk {
  return {
    id: 1,
    risk_id: 'RISK-001',
    title: 'Test Risk',
    description: null,
    category: null,
    status: 'open',
    owner_id: 1,
    owner: { id: 1, email: 'a@b.com', full_name: 'Owner', role: 'admin' },
    next_review_date: '2026-10-07',
    assessments: [
      {
        id: 1,
        likelihood: 3,
        impact: 3,
        risk_score: 9,
        residual_likelihood: null,
        residual_impact: null,
        residual_risk_score: null,
        notes: null,
        assessed_at: '2026-01-01T00:00:00Z',
      },
    ],
    current_score: 9,
    severity: 'medium',
    responses: [],
    history: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: null,
  } as unknown as Risk
}

async function renderPage() {
  render(
    <MemoryRouter initialEntries={['/risks/RISK-001']}>
      <Routes>
        <Route path="/risks/:riskId" element={<RiskDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByRole('heading', { name: 'Test Risk' })
}

describe('RiskDetailPage inline edits', () => {
  beforeEach(() => {
    mockedGet.mockReset()
    mockedUpdate.mockReset()
    mockedAddAssessment.mockReset()
    mockedGet.mockResolvedValue(makeRisk())
  })

  it('shows the next review date on its calendar day', async () => {
    await renderPage()
    expect(screen.getByText(new Date(2026, 9, 7).toLocaleDateString())).toBeInTheDocument()
  })

  it('shows the error when a status change is rejected', async () => {
    mockedUpdate.mockRejectedValueOnce(new ApiError(403, 'You can only edit risks you own.'))
    await renderPage()

    await userEvent.selectOptions(screen.getByLabelText('Change status'), 'closed')

    expect(await screen.findByRole('alert')).toHaveTextContent('You can only edit risks you own.')
  })

  it('shows the error inside the form when logging a review fails', async () => {
    mockedAddAssessment.mockRejectedValueOnce(new ApiError(422, 'Residual impact is required.'))
    await renderPage()

    await userEvent.click(screen.getByRole('button', { name: /log review/i }))
    await userEvent.click(screen.getByRole('button', { name: /save review/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Residual impact is required.')
    // The form stays open so the reviewer can fix and resubmit.
    expect(screen.getByRole('button', { name: /save review/i })).toBeInTheDocument()
  })

  it('keeps the page when the refresh after a successful save fails', async () => {
    mockedUpdate.mockResolvedValueOnce(makeRisk())
    await renderPage()
    mockedGet.mockRejectedValueOnce(new Error('network down'))

    await userEvent.selectOptions(screen.getByLabelText('Change status'), 'closed')

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not refresh/i)
    expect(screen.getByRole('heading', { name: 'Test Risk' })).toBeInTheDocument()
  })
})

describe('RiskDetailPage back link', () => {
  function RegisterProbe() {
    const location = useLocation()
    return <p data-testid="register-url">{location.pathname + location.search}</p>
  }

  beforeEach(() => {
    mockedGet.mockReset()
    mockedGet.mockResolvedValue(makeRisk())
    sessionStorage.clear()
  })

  it('returns to the register page and filters the user left', async () => {
    rememberRegisterSearch('?status=open&page=2')
    render(
      <MemoryRouter initialEntries={['/risks/RISK-001']}>
        <Routes>
          <Route path="/risks/:riskId" element={<RiskDetailPage />} />
          <Route path="/risks" element={<RegisterProbe />} />
        </Routes>
      </MemoryRouter>,
    )
    await screen.findByRole('heading', { name: 'Test Risk' })

    await userEvent.click(screen.getByRole('button', { name: 'Risk Register' }))

    expect(await screen.findByTestId('register-url')).toHaveTextContent('/risks?status=open&page=2')
  })
})
