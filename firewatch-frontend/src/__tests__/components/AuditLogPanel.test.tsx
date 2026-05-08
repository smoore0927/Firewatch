/**
 * Tests for the AuditLogPanel admin surface.
 *
 * The audit API client is mocked at the module level — we don't want real
 * fetches and we don't care about the request<T> wrapper here, just the
 * filter -> API call contract and the rendered states.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { AuditLog, AuditLogListResponse } from '@/types'

vi.mock('@/services/api', () => ({
  auditApi: {
    list: vi.fn(),
    listActions: vi.fn(),
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

import { auditApi, ApiError } from '@/services/api'
import AuditLogPanel from '@/components/settings/AuditLogPanel'

const mockedList = auditApi.list as unknown as ReturnType<typeof vi.fn>
const mockedListActions = auditApi.listActions as unknown as ReturnType<typeof vi.fn>

const SEVEN_DAYS_MS = 7 * 86_400_000
const THIRTY_DAYS_MS = 30 * 86_400_000

function makeLog(overrides: Partial<AuditLog> = {}): AuditLog {
  return {
    id: 1,
    user_id: 1,
    user_email: 'admin@example.com',
    action: 'risk.create',
    resource_type: 'risk',
    resource_id: '1',
    ip_address: '127.0.0.1',
    user_agent: null,
    details: null,
    created_at: new Date().toISOString(),
    ...overrides,
  }
}

function emptyResponse(total = 0): AuditLogListResponse {
  return { total, items: [] }
}

function listOf(items: AuditLog[], total?: number): AuditLogListResponse {
  return { total: total ?? items.length, items }
}

describe('AuditLogPanel', () => {
  beforeEach(() => {
    mockedList.mockReset()
    mockedListActions.mockReset()
    mockedListActions.mockResolvedValue({ actions: ['risk.create', 'risk.update', 'auth.login'] })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('initial load defaults to Last 7 days', async () => {
    mockedList.mockResolvedValue(emptyResponse())

    render(<AuditLogPanel />)

    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(1))

    const args = mockedList.mock.calls[0][0]
    expect(args).toEqual(
      expect.objectContaining({
        skip: 0,
        limit: 50,
        start: expect.any(String),
        end: expect.any(String),
      }),
    )
    expect(args.action).toBeUndefined()
    expect(args.resource_type).toBeUndefined()

    // start should be ~7 days before now (within 60s tolerance).
    const startMs = new Date(args.start).getTime()
    expect(Math.abs(Date.now() - SEVEN_DAYS_MS - startMs)).toBeLessThan(60_000)
    // end should be within 60s of now.
    const endMs = new Date(args.end).getTime()
    expect(Math.abs(Date.now() - endMs)).toBeLessThan(60_000)
  })

  it('empty state renders the correct message', async () => {
    mockedList.mockResolvedValue(emptyResponse())
    render(<AuditLogPanel />)

    expect(await screen.findByText('No audit events recorded yet.')).toBeInTheDocument()
  })

  it('loading state shows "Loading..."', async () => {
    let resolve: (value: AuditLogListResponse) => void = () => {}
    mockedList.mockImplementationOnce(
      () => new Promise<AuditLogListResponse>((r) => { resolve = r }),
    )

    render(<AuditLogPanel />)

    expect(await screen.findByText('Loading...')).toBeInTheDocument()

    resolve(emptyResponse())
    await waitFor(() => expect(screen.queryByText('Loading...')).not.toBeInTheDocument())
  })

  it('error state shows a friendly message on 403', async () => {
    mockedList.mockRejectedValueOnce(new ApiError(403, 'Forbidden'))

    render(<AuditLogPanel />)

    expect(
      await screen.findByText('You do not have permission to view audit logs.'),
    ).toBeInTheDocument()
  })

  it('Apply triggers a refetch with the new filters', async () => {
    const user = userEvent.setup()
    mockedList.mockResolvedValue(emptyResponse())

    render(<AuditLogPanel />)
    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(1))

    // Pick a resource type from the native select.
    await user.selectOptions(screen.getByLabelText('Resource type'), 'risk')

    // Pick an action via the SearchableSelect.
    // Wait for actionOptions to populate (listActions resolves on mount).
    await waitFor(() => expect(mockedListActions).toHaveBeenCalled())
    await user.click(screen.getByLabelText('Action'))
    await user.click(await screen.findByText('risk.create'))

    await user.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(2))
    const args = mockedList.mock.calls[1][0]
    expect(args).toEqual(
      expect.objectContaining({
        action: 'risk.create',
        resource_type: 'risk',
        skip: 0,
        limit: 50,
        start: expect.any(String),
        end: expect.any(String),
      }),
    )
    // Lookback preset is still 7d.
    const startMs = new Date(args.start).getTime()
    expect(Math.abs(Date.now() - SEVEN_DAYS_MS - startMs)).toBeLessThan(60_000)
  })

  it('lookback preset switching: 30d sends ~30d start; all sends no start/end', async () => {
    const user = userEvent.setup()
    mockedList.mockResolvedValue(emptyResponse())
    render(<AuditLogPanel />)
    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(1))

    // Switch to 30 days.
    await user.selectOptions(screen.getByLabelText('Look back'), '30d')
    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(2))
    let args = mockedList.mock.calls[1][0]
    expect(args.start).toEqual(expect.any(String))
    const startMs = new Date(args.start).getTime()
    expect(Math.abs(Date.now() - THIRTY_DAYS_MS - startMs)).toBeLessThan(60_000)

    // Switch to All time.
    await user.selectOptions(screen.getByLabelText('Look back'), 'all')
    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(3))
    args = mockedList.mock.calls[2][0]
    expect(args.start).toBeUndefined()
    expect(args.end).toBeUndefined()
  })

  it('Custom range reveals datetime inputs', async () => {
    const user = userEvent.setup()
    mockedList.mockResolvedValue(emptyResponse())
    render(<AuditLogPanel />)
    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(1))

    expect(screen.queryByLabelText('Start')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('End')).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Look back'), 'custom')

    expect(await screen.findByLabelText('Start')).toBeInTheDocument()
    expect(screen.getByLabelText('End')).toBeInTheDocument()
  })

  it('Custom range Apply uses the typed values', async () => {
    const user = userEvent.setup()
    mockedList.mockResolvedValue(emptyResponse())
    render(<AuditLogPanel />)
    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(1))

    await user.selectOptions(screen.getByLabelText('Look back'), 'custom')
    const startInput = await screen.findByLabelText('Start')
    const endInput = screen.getByLabelText('End')

    const startVal = '2026-01-01T00:00'
    const endVal = '2026-01-08T00:00'
    // datetime-local fields prefer fireEvent.change semantics; userEvent.type can be flaky.
    await user.click(startInput)
    await user.paste(startVal)
    await user.click(endInput)
    await user.paste(endVal)

    await user.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(2))
    const args = mockedList.mock.calls[1][0]
    expect(args.start).toBe(new Date(startVal).toISOString())
    expect(args.end).toBe(new Date(endVal).toISOString())
  })

  it('Clear resets to Last 7 days and empties the input fields', async () => {
    const user = userEvent.setup()
    mockedList.mockResolvedValue(emptyResponse())
    render(<AuditLogPanel />)
    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(1))

    // Apply a custom range first.
    await user.selectOptions(screen.getByLabelText('Look back'), 'custom')
    const startInput = await screen.findByLabelText('Start') as HTMLInputElement
    const endInput = screen.getByLabelText('End') as HTMLInputElement
    await user.click(startInput)
    await user.paste('2026-01-01T00:00')
    await user.click(endInput)
    await user.paste('2026-01-08T00:00')
    await user.selectOptions(screen.getByLabelText('Resource type'), 'risk')
    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(2))

    // Now Clear.
    await user.click(screen.getByRole('button', { name: 'Clear' }))
    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(3))
    const args = mockedList.mock.calls[2][0]
    expect(args.action).toBeUndefined()
    expect(args.resource_type).toBeUndefined()
    expect(args.start).toEqual(expect.any(String))
    const startMs = new Date(args.start).getTime()
    expect(Math.abs(Date.now() - SEVEN_DAYS_MS - startMs)).toBeLessThan(60_000)

    // Lookback flips back to '7d', so the custom inputs disappear.
    await waitFor(() => expect(screen.queryByLabelText('Start')).not.toBeInTheDocument())
    // Resource type select is cleared.
    expect((screen.getByLabelText('Resource type') as HTMLSelectElement).value).toBe('')
  })

  it('Pagination Next button advances skip', async () => {
    const user = userEvent.setup()
    const items: AuditLog[] = Array.from({ length: 50 }, (_, i) =>
      makeLog({ id: i + 1, action: 'risk.create' }),
    )
    mockedList.mockResolvedValue(listOf(items, 120))

    render(<AuditLogPanel />)
    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(1))
    // Wait for the rendered table — confirms the page rendered before clicking Next.
    await screen.findByText('Showing 1–50 of 120')

    await user.click(screen.getByRole('button', { name: 'Next' }))

    await waitFor(() => expect(mockedList).toHaveBeenCalledTimes(2))
    const args = mockedList.mock.calls[1][0]
    expect(args.skip).toBe(50)
    expect(args.limit).toBe(50)
  })

  it('action options refresh after each successful fetchLogs', async () => {
    mockedList.mockResolvedValue(emptyResponse())
    render(<AuditLogPanel />)

    // Once on mount (the standalone effect) and once inside fetchLogs.
    await waitFor(() => expect(mockedListActions).toHaveBeenCalledTimes(2))
  })

  it('renders rows when items are returned', async () => {
    const items = [
      makeLog({ id: 1, action: 'auth.login', user_email: 'alice@example.com' }),
      makeLog({ id: 2, action: 'risk.create', user_email: 'bob@example.com' }),
    ]
    mockedList.mockResolvedValue(listOf(items, 2))

    render(<AuditLogPanel />)

    const table = await screen.findByRole('table')
    expect(within(table).getByText('alice@example.com')).toBeInTheDocument()
    expect(within(table).getByText('bob@example.com')).toBeInTheDocument()
    expect(within(table).getByText('auth.login')).toBeInTheDocument()
    expect(within(table).getByText('risk.create')).toBeInTheDocument()
  })
})
