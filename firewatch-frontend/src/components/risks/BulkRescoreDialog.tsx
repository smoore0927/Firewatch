import { useEffect, useState } from 'react'
import { ApiError, risksApi } from '@/services/api'
import type { BulkRiskResult } from '@/types'
import { scoreLabel } from '@/types'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { X } from 'lucide-react'

interface Props {
  open: boolean
  riskIds: string[]
  onClose: () => void
  onDone: (result: BulkRiskResult) => void
}

const SCALE = [1, 2, 3, 4, 5] as const

export default function BulkRescoreDialog({ open, riskIds, onClose, onDone }: Props) {
  const [likelihood, setLikelihood] = useState<number>(3)
  const [impact, setImpact] = useState<number>(3)
  const [notes, setNotes] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setLikelihood(3)
      setImpact(3)
      setNotes('')
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

  const score = likelihood * impact

  async function handleConfirm() {
    setIsSubmitting(true)
    setError(null)
    try {
      const result = await risksApi.bulkRescore({
        risk_ids: riskIds,
        likelihood,
        impact,
        notes: notes.trim() || undefined,
      })
      onDone(result)
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save review, try again.')
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
        aria-labelledby="bulk-rescore-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="bulk-rescore-title" className="text-lg font-semibold">
              Log review
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Log a review for {riskIds.length} risk{riskIds.length === 1 ? '' : 's'}.
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
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="bulk-rescore-likelihood" className="text-sm font-medium">
                Likelihood <span aria-hidden="true" className="text-destructive">*</span>
              </label>
              <select
                id="bulk-rescore-likelihood"
                value={likelihood}
                onChange={(e) => setLikelihood(Number(e.target.value))}
                disabled={isSubmitting}
                aria-required="true"
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {SCALE.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="bulk-rescore-impact" className="text-sm font-medium">
                Impact <span aria-hidden="true" className="text-destructive">*</span>
              </label>
              <select
                id="bulk-rescore-impact"
                value={impact}
                onChange={(e) => setImpact(Number(e.target.value))}
                disabled={isSubmitting}
                aria-required="true"
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {SCALE.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="rounded-md border bg-muted/30 px-3 py-2 text-sm">
            Resulting score: <span className="font-semibold">{score}</span>
            <span className="text-muted-foreground"> — {scoreLabel(score)}</span>
          </div>

          <div>
            <label htmlFor="bulk-rescore-notes" className="text-sm font-medium">
              Notes <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <Textarea
              id="bulk-rescore-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              disabled={isSubmitting}
              placeholder="Why are these risks being reviewed?"
              className="mt-1"
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button type="button" onClick={handleConfirm} disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : 'Save review'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
