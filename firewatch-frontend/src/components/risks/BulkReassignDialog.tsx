import { useState } from 'react'
import { ApiError, risksApi, usersApi } from '@/services/api'
import type { BulkRiskResult, User } from '@/types'
import BulkActionDialog from './BulkActionDialog'

interface Props {
  open: boolean
  riskIds: string[]
  onClose: () => void
  onDone: (result: BulkRiskResult) => void
}

export default function BulkReassignDialog({ open, riskIds, onClose, onDone }: Readonly<Props>) {
  const [users, setUsers] = useState<User[]>([])
  const [ownerId, setOwnerId] = useState<number | ''>('')
  const [isLoadingUsers, setIsLoadingUsers] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  function reset() {
    setOwnerId('')
    setLoadError(null)
    setIsLoadingUsers(true)
    usersApi.listAssignable()
      .then(setUsers)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : 'Could not load users.'))
      .finally(() => setIsLoadingUsers(false))
  }

  return (
    <BulkActionDialog
      open={open}
      title="Reassign owner"
      description={`Set a new owner for ${riskIds.length} risk${riskIds.length === 1 ? '' : 's'}.`}
      confirmLabel="Reassign"
      submittingLabel="Reassigning…"
      errorFallback="Could not reassign, try again."
      confirmDisabled={ownerId === ''}
      onClose={onClose}
      onOpen={reset}
      onConfirm={() => risksApi.bulkReassign({ risk_ids: riskIds, owner_id: ownerId as number })}
      onDone={onDone}
    >
      {(disabled) => (
        <div>
          <label htmlFor="bulk-reassign-owner" className="text-sm font-medium">
            New owner <span aria-hidden="true" className="text-destructive">*</span>
          </label>
          <select
            id="bulk-reassign-owner"
            value={ownerId}
            onChange={(e) => setOwnerId(e.target.value ? Number(e.target.value) : '')}
            disabled={isLoadingUsers || disabled}
            aria-required="true"
            className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">{isLoadingUsers ? 'Loading…' : 'Select a user…'}</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name ? `${u.full_name} (${u.email})` : u.email}
              </option>
            ))}
          </select>
          {loadError && <p className="mt-2 text-sm text-destructive">{loadError}</p>}
        </div>
      )}
    </BulkActionDialog>
  )
}
