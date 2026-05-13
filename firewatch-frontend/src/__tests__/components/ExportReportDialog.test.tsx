import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { RiskReport } from '@/types'

vi.mock('@/services/api', () => ({
  reportsApi: {
    getRiskSummary: vi.fn(),
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

vi.mock('@/lib/pdf-report', () => ({
  generateRiskReportPdf: vi.fn(),
}))

import { reportsApi, ApiError } from '@/services/api'
import { generateRiskReportPdf } from '@/lib/pdf-report'
import ExportReportDialog from '@/components/dashboard/ExportReportDialog'

const mockedGet = reportsApi.getRiskSummary as unknown as ReturnType<typeof vi.fn>
const mockedGenerate = generateRiskReportPdf as unknown as ReturnType<typeof vi.fn>

const STUB_REPORT: RiskReport = {
  generated_at: '2026-05-08T12:00:00Z',
  generated_by: { id: 1, email: 'a@b.com', full_name: 'Test User', role: 'admin' },
  date_range: { start: '2026-01-01', end: '2026-02-01' },
  summary: {
    total: 0,
    by_status: {},
    by_severity: {},
    overdue_responses: 0,
    overdue_reviews: 0,
    risk_matrix: [],
  },
  score_history: { points: [] },
  risks: null,
}

describe('ExportReportDialog', () => {
  beforeEach(() => {
    mockedGet.mockReset()
    mockedGenerate.mockReset()
  })

  it('renders nothing when closed', () => {
    const { container } = render(
      <ExportReportDialog
        open={false}
        onClose={() => {}}
        defaultStart="2026-01-01"
        defaultEnd="2026-02-01"
        matrixEl={null}
        chartEl={null}
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('date inputs default to the provided props', () => {
    render(
      <ExportReportDialog
        open={true}
        onClose={() => {}}
        defaultStart="2026-01-01"
        defaultEnd="2026-02-01"
        matrixEl={null}
        chartEl={null}
      />,
    )

    const start = screen.getByLabelText('From') as HTMLInputElement
    const end = screen.getByLabelText('To') as HTMLInputElement
    expect(start.value).toBe('2026-01-01')
    expect(end.value).toBe('2026-02-01')
  })

  it('include risks toggle defaults to true and updates state', async () => {
    const user = userEvent.setup()
    render(
      <ExportReportDialog
        open={true}
        onClose={() => {}}
        defaultStart="2026-01-01"
        defaultEnd="2026-02-01"
        matrixEl={null}
        chartEl={null}
      />,
    )
    const toggle = screen.getByLabelText('Include risks in the register') as HTMLInputElement
    expect(toggle.checked).toBe(true)
    await user.click(toggle)
    expect(toggle.checked).toBe(false)
  })

  it('Generate PDF calls the API with current state and the helper, then closes', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    mockedGet.mockResolvedValueOnce(STUB_REPORT)
    mockedGenerate.mockResolvedValueOnce(undefined)

    const matrixEl = document.createElement('div')
    const chartEl = document.createElement('div')

    render(
      <ExportReportDialog
        open={true}
        onClose={onClose}
        defaultStart="2026-01-01"
        defaultEnd="2026-02-01"
        matrixEl={matrixEl}
        chartEl={chartEl}
      />,
    )

    // Toggle off so we can verify the boolean propagates as well.
    await user.click(screen.getByLabelText('Include risks in the register'))

    await user.click(screen.getByRole('button', { name: 'Generate PDF' }))

    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1))
    expect(mockedGet).toHaveBeenCalledWith('2026-01-01', '2026-02-01', false)

    await waitFor(() => expect(mockedGenerate).toHaveBeenCalledTimes(1))
    expect(mockedGenerate).toHaveBeenCalledWith(STUB_REPORT, { matrixEl, chartEl })

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('keeps the dialog open and reports an error on API failure', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const onError = vi.fn()
    mockedGet.mockRejectedValueOnce(new ApiError(500, 'Server exploded'))

    render(
      <ExportReportDialog
        open={true}
        onClose={onClose}
        defaultStart="2026-01-01"
        defaultEnd="2026-02-01"
        matrixEl={null}
        chartEl={null}
        onError={onError}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Generate PDF' }))

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Server exploded'))
    expect(onClose).not.toHaveBeenCalled()
    expect(mockedGenerate).not.toHaveBeenCalled()
  })

  it('Cancel button closes the dialog without calling the API', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()

    render(
      <ExportReportDialog
        open={true}
        onClose={onClose}
        defaultStart="2026-01-01"
        defaultEnd="2026-02-01"
        matrixEl={null}
        chartEl={null}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(mockedGet).not.toHaveBeenCalled()
  })
})
