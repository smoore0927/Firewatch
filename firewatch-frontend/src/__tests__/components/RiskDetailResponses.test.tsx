/**
 * Smoke tests for the Response Plans section on RiskDetailPage.
 *
 * Exercises the read-only vs editor split, add-response flow, delete confirm,
 * and the inline status quick-changer.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { Risk, User } from '@/types'

vi.mock('@/services/api', () => ({
  risksApi: {
    get: vi.fn(),
    addResponse: vi.fn(),
    updateResponse: vi.fn(),
    deleteResponse: vi.fn(),
  },
  usersApi: {
    listAssignable: vi.fn().mockResolvedValue([]),
  },
  ApiError: class ApiError extends Error {
    public status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
      this.name = 'ApiError'
    }
  },
}))

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

const VIEWER_USER: User = { ...ADMIN_USER, id: 2, email: 'viewer@example.com', full_name: 'Viewer', role: 'executive_viewer' }

let mockUser: User = ADMIN_USER

vi.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ user: mockUser, isLoading: false }),
}))

import { risksApi } from '@/services/api'
import RiskDetailPage from '@/pages/RiskDetailPage'

const mockedGet = risksApi.get as unknown as ReturnType<typeof vi.fn>
const mockedAdd = risksApi.addResponse as unknown as ReturnType<typeof vi.fn>
const mockedUpdate = risksApi.updateResponse as unknown as ReturnType<typeof vi.fn>
const mockedDelete = risksApi.deleteResponse as unknown as ReturnType<typeof vi.fn>

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
    next_review_date: null,
    assessments: [
      {
        id: 1,
        likelihood: 3,
        impact: 3,
        risk_score: 9,
        notes: null,
        assessed_at: '2026-01-01T00:00:00Z',
        assessed_by: { id: 1, email: 'a@b.com', full_name: 'Owner', role: 'admin' },
      },
    ],
    responses: [
      {
        id: 42,
        response_type: 'mitigate',
        status: 'planned',
        mitigation_strategy: 'Apply patches',
        target_date: '2026-12-01T00:00:00Z',
        completion_date: null,
        notes: null,
        owner_id: null,
        cost_estimate: null,
        start_date: null,
        created_at: '2026-01-01T00:00:00Z',
      },
    ],
    history: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  } as unknown as Risk
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/risks/RISK-001']}>
      <Routes>
        <Route path="/risks/:riskId" element={<RiskDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RiskDetailPage — Response Plans', () => {
  beforeEach(() => {
    mockedGet.mockReset()
    mockedAdd.mockReset()
    mockedUpdate.mockReset()
    mockedDelete.mockReset()
    mockUser = ADMIN_USER
    mockedGet.mockResolvedValue(makeRisk())
    mockedAdd.mockResolvedValue(makeRisk())
    mockedUpdate.mockResolvedValue(makeRisk())
    mockedDelete.mockResolvedValue(undefined)
  })

  it('renders responses read-only for a viewer (no edit affordances)', async () => {
    mockUser = VIEWER_USER
    renderPage()

    await waitFor(() => expect(screen.getByText('Apply patches')).toBeInTheDocument())

    expect(screen.queryByRole('button', { name: /add response/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit response 42/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /delete response 42/i })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/change response status/i)).not.toBeInTheDocument()
  })

  it('shows the "Add response" button for editors', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Apply patches')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /add response/i })).toBeInTheDocument()
  })

  it('opens the create form when "Add response" is clicked', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Apply patches')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: /add response/i }))

    expect(screen.getByLabelText(/mitigation strategy/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/response type/i)).toBeInTheDocument()
  })

  it('submits the create form via risksApi.addResponse', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Apply patches')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: /add response/i }))
    await userEvent.type(screen.getByLabelText(/mitigation strategy/i), 'New plan')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(mockedAdd).toHaveBeenCalledTimes(1))
    expect(mockedAdd).toHaveBeenCalledWith(
      'RISK-001',
      expect.objectContaining({
        response_type: 'mitigate',
        mitigation_strategy: 'New plan',
      }),
    )
  })

  it('calls risksApi.deleteResponse after the inline confirm', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Apply patches')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: /delete response 42/i }))
    await userEvent.click(screen.getByRole('button', { name: /yes, delete/i }))

    await waitFor(() => expect(mockedDelete).toHaveBeenCalledWith('RISK-001', 42))
  })

  it('quick-changes status via risksApi.updateResponse', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Apply patches')).toBeInTheDocument())

    const statusSelect = screen.getByLabelText(/change response status for response 42/i)
    await userEvent.selectOptions(statusSelect, 'completed')

    await waitFor(() => expect(mockedUpdate).toHaveBeenCalledTimes(1))
    expect(mockedUpdate).toHaveBeenCalledWith('RISK-001', 42, { status: 'completed' })
  })
})
