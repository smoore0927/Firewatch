import { useEffect, useState } from 'react'
import { ApiError, risksApi, usersApi } from '@/services/api'
import type { BulkRiskResult, User } from '@/types'
import { Button } from '@/components/ui/button'
import { X } from 'lucide-react'

interface Props {
  open: boolean
  riskIds: string[]
  onClose: () => void
  onDone: (result: BulkRiskResult) => void
}

export default function BulkReassignDialog({ open, riskIds, onClose, onDone }: Props) {
  const [users, setUsers] = useState<User[]>([])
  const [ownerId, setOwnerId] = useState<number | ''>('')
  const [isLoadingUsers, setIsLoadingUsers] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setError(null)
    setOwnerId('')
    setIsLoadingUsers(true)
    usersApi.listAssignable()
      .then((data) => setUsers(data))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Could not load users.')
      })
      .finally(() => setIsLoadingUsers(false))
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
    if (ownerId === '') return
    setIsSubmitting(true)
    setError(null)
    try {
      const result = await risksApi.bulkReassign({ risk_ids: riskIds, owner_id: ownerId })
      onDone(result)
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reassign, try again.')
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
        aria-labelledby="bulk-reassign-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="bulk-reassign-title" className="text-lg font-semibold">
              Reassign owner
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Set a new owner for {riskIds.length} risk{riskIds.length === 1 ? '' : 's'}.
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
          <div>
            <label htmlFor="bulk-reassign-owner" className="text-sm font-medium">
              New owner <span aria-hidden="true" className="text-destructive">*</span>
            </label>
            <select
              id="bulk-reassign-owner"
              value={ownerId}
              onChange={(e) => setOwnerId(e.target.value ? Number(e.target.value) : '')}
              disabled={isLoadingUsers || isSubmitting}
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
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button type="button" onClick={handleConfirm} disabled={ownerId === '' || isSubmitting}>
              {isSubmitting ? 'Reassigning…' : 'Reassign'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
