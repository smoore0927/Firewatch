import { useEffect, useState, type ReactNode } from 'react'
import { errorMessage } from '@/services/api'
import type { BulkRiskResult } from '@/types'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'

interface BulkActionDialogProps {
  open: boolean
  title: string
  description: ReactNode
  confirmLabel: string
  submittingLabel: string
  /** Fallback message when the failed request is not an ApiError. */
  errorFallback: string
  /** Disables the confirm button (e.g. a required field is empty). */
  confirmDisabled?: boolean
  onClose: () => void
  /** Performs the bulk mutation and resolves with its result. */
  onConfirm: () => Promise<BulkRiskResult>
  onDone: (result: BulkRiskResult) => void
  /** Reset wrapper-owned form state whenever the dialog (re)opens. */
  onOpen?: () => void
  /** The dialog's field(s); receives whether the form is mid-submit. */
  children: (disabled: boolean) => ReactNode
}

/**
 * Shared shell for the bulk risk-action dialogs (reassign / status / rescore).
 * Owns the submit lifecycle (busy state, error capture, onDone+close) and the
 * footer; each caller supplies only its own fields and mutation.
 */
export default function BulkActionDialog({
  open,
  title,
  description,
  confirmLabel,
  submittingLabel,
  errorFallback,
  confirmDisabled = false,
  onClose,
  onConfirm,
  onDone,
  onOpen,
  children,
}: Readonly<BulkActionDialogProps>) {
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setIsSubmitting(false)
    setError(null)
    onOpen?.()
    // Re-runs only when the dialog opens; onOpen is intentionally excluded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  async function handleConfirm() {
    setIsSubmitting(true)
    setError(null)
    try {
      const result = await onConfirm()
      onDone(result)
      onClose()
    } catch (err) {
      setError(errorMessage(err, errorFallback))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={title} description={description} busy={isSubmitting}>
      <div className="space-y-4">
        {children(isSubmitting)}

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="button" onClick={handleConfirm} disabled={isSubmitting || confirmDisabled}>
            {isSubmitting ? submittingLabel : confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
