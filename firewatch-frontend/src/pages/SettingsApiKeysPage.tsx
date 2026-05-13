import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Check, Copy, Plus, Trash2, X } from 'lucide-react'
import { apiKeysApi, ApiError } from '@/services/api'
import type { ApiKey, ApiKeyCreated, ApiKeyWithOwner } from '@/types'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/context/AuthContext'

type ApiKeyRow = ApiKey | ApiKeyWithOwner

function hasOwner(key: ApiKeyRow): key is ApiKeyWithOwner {
  return 'owner' in key
}

const EXPIRATION_OPTIONS: { value: string; label: string; days: number | null }[] = [
  { value: 'never', label: 'Never', days: null },
  { value: '30', label: '30 days', days: 30 },
  { value: '90', label: '90 days', days: 90 },
  { value: '180', label: '180 days', days: 180 },
  { value: '365', label: '365 days', days: 365 },
]

type KeyStatus = 'revoked' | 'expired' | 'active'

function statusOf(key: ApiKeyRow, nowMs: number): KeyStatus {
  if (key.revoked_at) return 'revoked'
  if (key.expires_at && Date.parse(key.expires_at) < nowMs) return 'expired'
  return 'active'
}

function formatDate(iso: string | null): React.ReactNode {
  if (!iso) return <span className="text-muted-foreground">—</span>
  return new Date(iso).toLocaleString()
}

export default function SettingsApiKeysPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [keys, setKeys] = useState<ApiKeyRow[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [flashId, setFlashId] = useState<number | null>(null)
  const [pendingId, setPendingId] = useState<number | null>(null)
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [revealedKey, setRevealedKey] = useState<ApiKeyCreated | null>(null)
  const [showAllUsers, setShowAllUsers] = useState(false)
  const [filter, setFilter] = useState('')

  const fetchKeys = useCallback(() => {
    setIsLoading(true)
    setError(null)
    const promise: Promise<ApiKeyRow[]> = showAllUsers
      ? apiKeysApi.listAll()
      : apiKeysApi.list()
    promise
      .then((data) => setKeys(data))
      .catch((err) => {
        if (err instanceof ApiError) setError(err.message)
        else setError('Could not load API keys. Try again.')
      })
      .finally(() => setIsLoading(false))
  }, [showAllUsers])

  useEffect(() => { fetchKeys() }, [fetchKeys])

  async function handleRevoke(target: ApiKeyRow) {
    const confirmed = globalThis.confirm(
      'Revoke this key? Applications using it will stop working immediately.',
    )
    if (!confirmed) return
    setError(null)
    setPendingId(target.id)
    const previous = keys
    const revokedAt = new Date().toISOString()
    setKeys((prev) => prev.map((k) => (k.id === target.id ? { ...k, revoked_at: revokedAt } : k)))
    try {
      await apiKeysApi.revoke(target.id)
      setFlashId(target.id)
      globalThis.setTimeout(() => {
        setFlashId((current) => (current === target.id ? null : current))
      }, 2000)
    } catch (err) {
      setKeys(previous)
      if (err instanceof ApiError) setError(err.message)
      else setError('Could not revoke key. Try again.')
      fetchKeys()
    } finally {
      setPendingId((current) => (current === target.id ? null : current))
    }
  }

  function handleKeyCreated(created: ApiKeyCreated) {
    setIsCreateOpen(false)
    setRevealedKey(created)
    fetchKeys()
  }

  function handleRevealClose() {
    setRevealedKey(null)
  }

  const nowMs = Date.now()

  const normalizedFilter = filter.trim().toLowerCase()
  const visibleKeys = normalizedFilter
    ? keys.filter((k) => (
        k.name.toLowerCase().includes(normalizedFilter) ||
        k.prefix.toLowerCase().includes(normalizedFilter)
      ))
    : keys

  const showOwnerColumn = showAllUsers && isAdmin
  const columnCount = showOwnerColumn ? 8 : 7

  let emptyStateMessage: string
  if (normalizedFilter) {
    emptyStateMessage = 'No keys match this filter.'
  } else {
    emptyStateMessage = 'No API keys yet. Create one to get started.'
  }

  let headerDescription: string
  if (showOwnerColumn) {
    headerDescription = 'All API keys across all users. Use the filter to find a leaked key by prefix.'
  } else {
    headerDescription = 'Create personal API keys for programmatic access. Keys inherit your role and are shown only once at creation.'
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">API keys</h2>
          <p className="text-muted-foreground text-sm">
            {headerDescription}
          </p>
        </div>
        <Button
          type="button"
          onClick={() => setIsCreateOpen(true)}
          className="gap-2"
        >
          <Plus className="h-4 w-4" />
          Create key
        </Button>
      </div>

      {error && (
        <Card className="p-4 border-destructive/50">
          <p role="alert" className="text-destructive text-sm">{error}</p>
        </Card>
      )}

      <div className="flex items-center gap-3">
        <Input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by name or key prefix"
          className="max-w-md"
          aria-label="Filter API keys by name or prefix"
        />
        {isAdmin && (
          <div className="flex items-center gap-2 ml-auto">
            <input
              id="show-all-users-keys"
              type="checkbox"
              checked={showAllUsers}
              onChange={(e) => setShowAllUsers(e.target.checked)}
              className="h-4 w-4 rounded border-input"
            />
            <Label htmlFor="show-all-users-keys" className="text-sm font-normal cursor-pointer">
              Show all users' keys
            </Label>
          </div>
        )}
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <p className="text-muted-foreground text-sm">Loading API keys...</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Name</th>
                  {showOwnerColumn && (
                    <th className="px-4 py-3 text-left font-medium">Owner</th>
                  )}
                  <th className="px-4 py-3 text-left font-medium">Key prefix</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3 text-left font-medium">Created</th>
                  <th className="px-4 py-3 text-left font-medium">Last used</th>
                  <th className="px-4 py-3 text-left font-medium">Expires</th>
                  <th className="px-4 py-3 text-left font-medium w-20"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {visibleKeys.length === 0 ? (
                  <tr>
                    <td
                      colSpan={columnCount}
                      className="px-4 py-10 text-center text-muted-foreground"
                    >
                      {emptyStateMessage}
                    </td>
                  </tr>
                ) : (
                  visibleKeys.map((k) => {
                    const status = statusOf(k, nowMs)
                    const isPending = pendingId === k.id
                    const showFlash = flashId === k.id
                    const revokeDisabled = isPending || status !== 'active'
                    return (
                      <tr key={k.id} className="hover:bg-muted/40 transition-colors">
                        <td className="px-4 py-3">{k.name}</td>
                        {showOwnerColumn && (
                          <td className="px-4 py-3">
                            {hasOwner(k) ? (
                              <div className="flex flex-col">
                                <span className="font-mono text-xs">{k.owner.email}</span>
                                {k.owner.full_name && (
                                  <span className="text-xs text-muted-foreground">
                                    {k.owner.full_name}
                                  </span>
                                )}
                              </div>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </td>
                        )}
                        <td className="px-4 py-3">
                          <span className="font-mono text-xs">
                            fwk_…{k.prefix}…
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={status} />
                        </td>
                        <td className="px-4 py-3">{formatDate(k.created_at)}</td>
                        <td className="px-4 py-3">{formatDate(k.last_used_at)}</td>
                        <td className="px-4 py-3">{formatDate(k.expires_at)}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => handleRevoke(k)}
                              disabled={revokeDisabled}
                              title="Revoke key"
                              aria-label="Revoke key"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                            {showFlash && (
                              <Check
                                className="h-4 w-4 text-green-600"
                                aria-label="Key updated"
                              />
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <CreateApiKeyDialog
        open={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onCreated={handleKeyCreated}
      />

      <RevealApiKeyDialog
        created={revealedKey}
        onClose={handleRevealClose}
      />
    </div>
  )
}

interface StatusBadgeProps {
  status: KeyStatus
}

function StatusBadge({ status }: Readonly<StatusBadgeProps>) {
  if (status === 'revoked') {
    return <Badge variant="outline">Revoked</Badge>
  }
  if (status === 'expired') {
    return <Badge variant="outline">Expired</Badge>
  }
  return <Badge variant="default">Active</Badge>
}

interface CreateApiKeyDialogProps {
  open: boolean
  onClose: () => void
  onCreated: (created: ApiKeyCreated) => void
}

function CreateApiKeyDialog({ open, onClose, onCreated }: Readonly<CreateApiKeyDialogProps>) {
  const [name, setName] = useState('')
  const [expirationValue, setExpirationValue] = useState<string>('never')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setName('')
      setExpirationValue('never')
      setError(null)
      setIsSubmitting(false)
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

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (isSubmitting) return
    setError(null)
    setIsSubmitting(true)
    try {
      const selected = EXPIRATION_OPTIONS.find((o) => o.value === expirationValue)
      const expiresInDays = selected ? selected.days : null
      const created = await apiKeysApi.create({
        name: name.trim(),
        expires_in_days: expiresInDays,
      })
      onCreated(created)
    } catch (err) {
      if (err instanceof ApiError) setError(err.message)
      else setError('Could not create API key. Try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <dialog
        open
        className="static m-0 w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg"
        aria-modal="true"
        aria-labelledby="create-api-key-dialog-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="create-api-key-dialog-title" className="text-lg font-semibold">
              Create API key
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              The plaintext key is shown only once after creation. Store it somewhere safe.
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

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="create-api-key-name">Name</Label>
            <Input
              id="create-api-key-name"
              type="text"
              required
              maxLength={120}
              autoComplete="off"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isSubmitting}
              placeholder="e.g. CI deployment bot"
            />
            <p className="text-xs text-muted-foreground">
              A human-readable label. Up to 120 characters.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="create-api-key-expires">Expires in</Label>
            <select
              id="create-api-key-expires"
              value={expirationValue}
              onChange={(e) => setExpirationValue(e.target.value)}
              disabled={isSubmitting}
              className="flex h-9 w-full max-w-[14rem] rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              {EXPIRATION_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3">
              <p role="alert" className="text-sm text-destructive">{error}</p>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting || !name.trim()}
            >
              {isSubmitting ? 'Creating…' : 'Create key'}
            </Button>
          </div>
        </form>
      </dialog>
    </div>
  )
}

interface RevealApiKeyDialogProps {
  created: ApiKeyCreated | null
  onClose: () => void
}

function RevealApiKeyDialog({ created, onClose }: Readonly<RevealApiKeyDialogProps>) {
  const [copied, setCopied] = useState(false)

  const isOpen = created !== null

  useEffect(() => {
    if (!isOpen) {
      setCopied(false)
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    globalThis.addEventListener('keydown', onKey)
    return () => globalThis.removeEventListener('keydown', onKey)
  }, [isOpen, onClose])

  if (!created) return null

  async function handleCopy() {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.key)
      setCopied(true)
      globalThis.setTimeout(() => {
        setCopied(false)
      }, 2000)
    } catch {
      // Clipboard write may fail in insecure contexts; the user can still select manually.
      setCopied(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <dialog
        open
        className="static m-0 w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg"
        aria-modal="true"
        aria-labelledby="reveal-api-key-dialog-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="reveal-api-key-dialog-title" className="text-lg font-semibold">
              Your new API key
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {created.name}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-6 space-y-4">
          <div className="flex items-start gap-3 rounded-md border border-amber-500/50 bg-amber-500/10 p-3">
            <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600" aria-hidden="true" />
            <p className="text-sm">
              Copy this key now — it will not be shown again. If you lose it, you'll need to
              create a new key.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="reveal-api-key-value">API key</Label>
            <div className="flex gap-2">
              <Input
                id="reveal-api-key-value"
                type="text"
                readOnly
                value={created.key}
                onFocus={(e) => e.currentTarget.select()}
                className="font-mono text-xs"
              />
              <Button
                type="button"
                variant="outline"
                onClick={handleCopy}
                className="gap-2 shrink-0"
              >
                <Copy className="h-4 w-4" />
                {copied ? 'Copied!' : 'Copy'}
              </Button>
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <Button type="button" onClick={onClose}>
              I've saved my key
            </Button>
          </div>
        </div>
      </dialog>
    </div>
  )
}
