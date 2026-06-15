import { useState } from 'react'
import { risksApi } from '@/services/api'
import type { BulkRiskResult, RiskStatus } from '@/types'
import { RISK_STATUS_LABELS } from '@/lib/constants'
import BulkActionDialog from './BulkActionDialog'

interface Props {
  open: boolean
  riskIds: string[]
  onClose: () => void
  onDone: (result: BulkRiskResult) => void
}

export default function BulkStatusDialog({ open, riskIds, onClose, onDone }: Readonly<Props>) {
  const [status, setStatus] = useState<RiskStatus>('open')

  return (
    <BulkActionDialog
      open={open}
      title="Change status"
      description={`Update the status of ${riskIds.length} risk${riskIds.length === 1 ? '' : 's'}.`}
      confirmLabel="Update status"
      submittingLabel="Updating…"
      errorFallback="Could not update risks, try again."
      onClose={onClose}
      onOpen={() => setStatus('open')}
      onConfirm={() => risksApi.bulkSetStatus({ risk_ids: riskIds, status })}
      onDone={onDone}
    >
      {(disabled) => (
        <div className="space-y-1">
          <label htmlFor="bulk-status-select" className="text-xs font-medium">
            Status <span aria-hidden="true" className="text-destructive">*</span>
          </label>
          <select
            id="bulk-status-select"
            value={status}
            onChange={(e) => setStatus(e.target.value as RiskStatus)}
            disabled={disabled}
            aria-required="true"
            className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          >
            {(Object.keys(RISK_STATUS_LABELS) as RiskStatus[]).map((s) => (
              <option key={s} value={s}>{RISK_STATUS_LABELS[s]}</option>
            ))}
          </select>
        </div>
      )}
    </BulkActionDialog>
  )
}
