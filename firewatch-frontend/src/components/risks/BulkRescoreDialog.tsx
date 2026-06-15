import { useState } from 'react'
import { risksApi } from '@/services/api'
import type { BulkRiskResult } from '@/types'
import { scoreLabel } from '@/types'
import { Textarea } from '@/components/ui/textarea'
import BulkActionDialog from './BulkActionDialog'

interface Props {
  open: boolean
  riskIds: string[]
  onClose: () => void
  onDone: (result: BulkRiskResult) => void
}

const SCALE = [1, 2, 3, 4, 5] as const

export default function BulkRescoreDialog({ open, riskIds, onClose, onDone }: Readonly<Props>) {
  const [likelihood, setLikelihood] = useState<number>(3)
  const [impact, setImpact] = useState<number>(3)
  const [notes, setNotes] = useState('')

  const score = likelihood * impact

  function reset() {
    setLikelihood(3)
    setImpact(3)
    setNotes('')
  }

  return (
    <BulkActionDialog
      open={open}
      title="Log review"
      description={`Log a review for ${riskIds.length} risk${riskIds.length === 1 ? '' : 's'}.`}
      confirmLabel="Save review"
      submittingLabel="Saving…"
      errorFallback="Could not save review, try again."
      onClose={onClose}
      onOpen={reset}
      onConfirm={() => risksApi.bulkRescore({
        risk_ids: riskIds,
        likelihood,
        impact,
        notes: notes.trim() || undefined,
      })}
      onDone={onDone}
    >
      {(disabled) => (
        <>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="bulk-rescore-likelihood" className="text-sm font-medium">
                Likelihood <span aria-hidden="true" className="text-destructive">*</span>
              </label>
              <select
                id="bulk-rescore-likelihood"
                value={likelihood}
                onChange={(e) => setLikelihood(Number(e.target.value))}
                disabled={disabled}
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
                disabled={disabled}
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
              disabled={disabled}
              placeholder="Why are these risks being reviewed?"
              className="mt-1"
            />
          </div>
        </>
      )}
    </BulkActionDialog>
  )
}
