/**
 * NotificationBell behaviour tests.
 *
 * Covers the bell badge, dropdown opening, mark-all-read, row click navigation,
 * and the empty state. Mocks the notifications API directly so we never hit
 * the network.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { NotificationItem } from '@/types'

vi.mock('@/services/api', () => ({
  notificationsApi: {
    unreadCount: vi.fn(),
    list: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  },
}))

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

import { notificationsApi } from '@/services/api'
import NotificationBell from '@/components/layout/NotificationBell'

const unreadCountMock = notificationsApi.unreadCount as unknown as ReturnType<typeof vi.fn>
const listMock = notificationsApi.list as unknown as ReturnType<typeof vi.fn>
const markReadMock = notificationsApi.markRead as unknown as ReturnType<typeof vi.fn>
const markAllReadMock = notificationsApi.markAllRead as unknown as ReturnType<typeof vi.fn>

function makeNotification(overrides: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id: 1,
    type: 'risk_assigned',
    risk_id: 42,
    risk_human_id: 'RISK-042',
    title: 'You were assigned a risk',
    message: 'RISK-042 — Sample risk title',
    link: '/risks/RISK-042',
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    read_at: null,
    ...overrides,
  }
}

function renderBell() {
  return render(
    <MemoryRouter>
      <NotificationBell />
    </MemoryRouter>,
  )
}

describe('NotificationBell', () => {
  beforeEach(() => {
    unreadCountMock.mockReset()
    listMock.mockReset()
    markReadMock.mockReset()
    markAllReadMock.mockReset()
    mockNavigate.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the bell with the unread badge', async () => {
    unreadCountMock.mockResolvedValue({ count: 3 })

    renderBell()

    expect(await screen.findByTestId('notification-badge')).toHaveTextContent('3')
  })

  it('hides the badge when there are no unread notifications', async () => {
    unreadCountMock.mockResolvedValue({ count: 0 })

    renderBell()

    await waitFor(() => expect(unreadCountMock).toHaveBeenCalled())
    expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument()
  })

  it('shows "9+" when unread count exceeds 9', async () => {
    unreadCountMock.mockResolvedValue({ count: 17 })

    renderBell()

    expect(await screen.findByTestId('notification-badge')).toHaveTextContent('9+')
  })

  it('opens the dropdown and fetches the list on click', async () => {
    unreadCountMock.mockResolvedValue({ count: 1 })
    listMock.mockResolvedValue({
      items: [makeNotification()],
      total: 1,
      unread_total: 1,
    })

    renderBell()

    await waitFor(() => expect(unreadCountMock).toHaveBeenCalled())
    await userEvent.click(screen.getByRole('button', { name: /notifications/i }))

    await waitFor(() => expect(listMock).toHaveBeenCalledWith({ limit: 20 }))
    expect(await screen.findByText('You were assigned a risk')).toBeInTheDocument()
  })

  it('marks all read and zeroes the badge', async () => {
    unreadCountMock.mockResolvedValue({ count: 2 })
    listMock
      .mockResolvedValueOnce({
        items: [makeNotification({ id: 1 }), makeNotification({ id: 2, title: 'Second' })],
        total: 2,
        unread_total: 2,
      })
      .mockResolvedValueOnce({
        items: [
          makeNotification({ id: 1, read_at: new Date().toISOString() }),
          makeNotification({ id: 2, title: 'Second', read_at: new Date().toISOString() }),
        ],
        total: 2,
        unread_total: 0,
      })
    markAllReadMock.mockResolvedValue({ marked: 2 })

    renderBell()

    await waitFor(() => expect(unreadCountMock).toHaveBeenCalled())
    await userEvent.click(screen.getByRole('button', { name: /notifications/i }))
    await screen.findByText('You were assigned a risk')

    await userEvent.click(screen.getByRole('button', { name: /mark all read/i }))

    await waitFor(() => expect(markAllReadMock).toHaveBeenCalled())
    await waitFor(() =>
      expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument(),
    )
  })

  it('navigates and marks the row read when a notification is clicked', async () => {
    unreadCountMock.mockResolvedValue({ count: 1 })
    listMock.mockResolvedValue({
      items: [makeNotification()],
      total: 1,
      unread_total: 1,
    })
    markReadMock.mockResolvedValue(undefined)

    renderBell()

    await waitFor(() => expect(unreadCountMock).toHaveBeenCalled())
    await userEvent.click(screen.getByRole('button', { name: /notifications/i }))

    const row = await screen.findByText('You were assigned a risk')
    await userEvent.click(row)

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/risks/RISK-042'))
    await waitFor(() => expect(markReadMock).toHaveBeenCalledWith(1))
  })

  it('renders the empty state when there are no notifications', async () => {
    unreadCountMock.mockResolvedValue({ count: 0 })
    listMock.mockResolvedValue({ items: [], total: 0, unread_total: 0 })

    renderBell()

    await waitFor(() => expect(unreadCountMock).toHaveBeenCalled())
    await userEvent.click(screen.getByRole('button', { name: /notifications/i }))

    expect(await screen.findByText(/all caught up/i)).toBeInTheDocument()
  })
})
