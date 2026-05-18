import { useEffect, useState } from 'react'
import { ApiError, risksApi } from '@/services/api'
import type { BulkRiskResult } from '@/types'
import { Button } from '@/components/ui/button'
import { X } from 'lucide-react'

interface Props {
  open: boolean
  riskIds: string[]
  onClose: () => void
  onDone: (result: BulkRiskResult) => void
}

export default function BulkCloseDialog({ open, riskIds, onClose, onDone }: Props) {
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setIsSubmitting(false)
      setError(null)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !isSubmitting) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, isSubmitting, onClose])

  if (!open) return null

  async function handleConfirm() {
    setIsSubmitting(true)
    setError(null)
    try {
      const result = await risksApi.bulkSetStatus({ risk_ids: riskIds, status: 'closed' })
      onDone(result)
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not close risks, try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={() => { if (!isSubmitting) onClose() }}
    >
      <div
        className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="bulk-close-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="bulk-close-title" className="text-lg font-semibold">
              Close risks
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Close {riskIds.length} risk{riskIds.length === 1 ? '' : 's'}? This will set their status to Closed.
            </p>
          </div>
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

        <div className="mt-6 space-y-4">
          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button type="button" onClick={handleConfirm} disabled={isSubmitting}>
              {isSubmitting ? 'Closing…' : 'Close risks'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
