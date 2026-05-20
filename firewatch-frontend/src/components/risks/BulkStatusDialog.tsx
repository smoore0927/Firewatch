import { SyntheticEvent, useEffect, useRef, useState } from 'react'
import { ApiError, risksApi } from '@/services/api'
import type { BulkRiskResult, RiskStatus } from '@/types'
import { Button } from '@/components/ui/button'
import { X } from 'lucide-react'

interface Props {
  open: boolean
  riskIds: string[]
  onClose: () => void
  onDone: (result: BulkRiskResult) => void
}

const STATUS_LABELS: Record<RiskStatus, string> = {
  open:        'Open',
  in_progress: 'In Progress',
  mitigated:   'Mitigated',
  accepted:    'Accepted',
  closed:      'Closed',
}

export default function BulkStatusDialog({ open, riskIds, onClose, onDone }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const [status, setStatus] = useState<RiskStatus>('open')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setStatus('open')
      setIsSubmitting(false)
      setError(null)
      ref.current?.showModal()
    }
  }, [open])

  function handleCancelEvent(e: SyntheticEvent<HTMLDialogElement>) {
    if (isSubmitting) e.preventDefault()
  }

  async function handleConfirm() {
    setIsSubmitting(true)
    setError(null)
    try {
      const result = await risksApi.bulkSetStatus({ risk_ids: riskIds, status })
      onDone(result)
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update risks, try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="bulk-status-title"
      onCancel={handleCancelEvent}
      onClose={onClose}
      className="bg-background rounded-lg border shadow-lg max-w-lg w-full mx-4 p-6 space-y-4 backdrop:bg-black/50"
    >
      <div className="flex items-start justify-between gap-4">
        <h3 id="bulk-status-title" className="font-semibold text-base">Change status</h3>
        <button
          type="button"
          onClick={() => ref.current?.close()}
          disabled={isSubmitting}
          className="text-muted-foreground hover:text-foreground disabled:opacity-50"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          Change status of {riskIds.length} risk{riskIds.length === 1 ? '' : 's'} to {STATUS_LABELS[status]}?
        </p>
        <div className="space-y-1">
          <label htmlFor="bulk-status-select" className="text-xs font-medium">Status</label>
          <select
            id="bulk-status-select"
            value={status}
            onChange={(e) => setStatus(e.target.value as RiskStatus)}
            disabled={isSubmitting}
            className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          >
            {(Object.keys(STATUS_LABELS) as RiskStatus[]).map((s) => (
              <option key={s} value={s}>{STATUS_LABELS[s]}</option>
            ))}
          </select>
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isSubmitting}
          onClick={() => ref.current?.close()}
        >
          Cancel
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={isSubmitting}
          onClick={handleConfirm}
        >
          {isSubmitting ? 'Updating…' : 'Update status'}
        </Button>
      </div>
    </dialog>
  )
}
