/**
 * Smoke test for the bulk action bar on RisksPage.
 *
 * The bar is hidden when no risks are selected and appears once one or more
 * checkboxes are ticked. We only assert visibility here — the dialog flows
 * are exercised by manual walkthrough.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Risk, User } from '@/types'

vi.mock('@/services/api', () => ({
  risksApi: {
    list: vi.fn(),
    exportCsv: vi.fn(),
    bulkReassign: vi.fn(),
    bulkSetStatus: vi.fn(),
    bulkRescore: vi.fn(),
  },
  usersApi: {
    listAssignable: vi.fn(),
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

vi.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ user: mockUser, isLoading: false }),
}))

let mockUser: User = ADMIN_USER

import { risksApi } from '@/services/api'
import RisksPage from '@/pages/RisksPage'

const mockedList = risksApi.list as unknown as ReturnType<typeof vi.fn>

function makeRisk(id: number): Risk {
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
    response_due_date: null,
    response_type: null,
    response_status: null,
    response_notes: null,
    assessments: [
      {
        id,
        likelihood: 3,
        impact: 3,
        risk_score: 9,
        notes: null,
        assessed_at: '2026-01-01T00:00:00Z',
        assessed_by: { id: 1, email: 'a@b.com', full_name: 'Owner', role: 'admin' },
      },
    ],
    responses: [],
    history: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  } as unknown as Risk
}

describe('RisksPage bulk action bar', () => {
  beforeEach(() => {
    mockedList.mockReset()
    mockUser = ADMIN_USER
  })

  it('hides the bulk bar when nothing is selected and shows it after a checkbox tick', async () => {
    mockedList.mockResolvedValue({ items: [makeRisk(1), makeRisk(2)], total: 2 })

    render(
      <MemoryRouter>
        <RisksPage />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('Risk 1')).toBeInTheDocument())

    expect(screen.queryByText(/selected/i)).not.toBeInTheDocument()

    const rowCheckbox = screen.getByLabelText('Select RISK-001')
    await userEvent.click(rowCheckbox)

    expect(await screen.findByText('1 selected')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reassign owner/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^close…$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /re-score/i })).toBeInTheDocument()
  })

  it('hides the reassign button for risk_owner role', async () => {
    mockUser = { ...ADMIN_USER, role: 'risk_owner' }
    mockedList.mockResolvedValue({ items: [makeRisk(1)], total: 1 })

    render(
      <MemoryRouter>
        <RisksPage />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('Risk 1')).toBeInTheDocument())
    await userEvent.click(screen.getByLabelText('Select RISK-001'))

    expect(await screen.findByText('1 selected')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reassign owner/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^close…$/i })).toBeInTheDocument()
  })

  it('does not render selection checkboxes for executive_viewer', async () => {
    mockUser = VIEWER_USER
    mockedList.mockResolvedValue({ items: [makeRisk(1)], total: 1 })

    render(
      <MemoryRouter>
        <RisksPage />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('Risk 1')).toBeInTheDocument())
    expect(screen.queryByLabelText('Select RISK-001')).not.toBeInTheDocument()
  })
})
