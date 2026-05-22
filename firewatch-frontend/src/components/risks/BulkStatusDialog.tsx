import { useEffect, useState } from 'react'
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

export default function BulkStatusDialog({ open, riskIds, onClose, onDone }: Readonly<Props>) {
  const [status, setStatus] = useState<RiskStatus>('open')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setStatus('open')
      setIsSubmitting(false)
      setError(null)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !isSubmitting) onClose()
    }
    globalThis.addEventListener('keydown', onKey)
    return () => globalThis.removeEventListener('keydown', onKey)
  }, [open, isSubmitting, onClose])

  if (!open) return null

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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Close dialog"
        disabled={isSubmitting}
        onClick={onClose}
        className="absolute inset-0 bg-black/50"
      />
      <dialog
        open
        style={{ margin: 0 }}
        className="relative w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg"
        aria-labelledby="bulk-status-title"
      >
        <div className="flex items-start justify-between gap-4">
          <h3 id="bulk-status-title" className="font-semibold text-base">Change status</h3>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="text-muted-foreground hover:text-foreground disabled:opacity-50"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4 space-y-3 text-sm">
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

        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

        <div className="mt-4 flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isSubmitting}
            onClick={onClose}
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
    </div>
  )
}
