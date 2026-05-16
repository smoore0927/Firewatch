import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  Check,
  Copy,
  Eye,
  EyeOff,
  History,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  X,
  Zap,
} from 'lucide-react'
import { webhooksApi, ApiError } from '@/services/api'
import type {
  WebhookDelivery,
  WebhookSubscription,
  WebhookSubscriptionCreate,
  WebhookSubscriptionCreated,
  WebhookSubscriptionUpdate,
  WebhookEventType,
} from '@/types'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const SUBSCRIBABLE_EVENTS: { value: WebhookEventType; label: string; description: string }[] = [
  {
    value: 'risk.assigned',
    label: 'risk.assigned',
    description: 'Fires when a risk is assigned to an owner.',
  },
  {
    value: 'review.overdue',
    label: 'review.overdue',
    description: 'Fires daily for risks whose review window has elapsed.',
  },
  {
    value: 'response.overdue',
    label: 'response.overdue',
    description: 'Fires daily for responses past their target completion date.',
  },
]

const VERIFICATION_SNIPPET = `Header: X-Firewatch-Signature: sha256=<hex>
The signature is HMAC-SHA256 over \`\${timestamp}.\${body}\` using your secret.`

function formatDate(iso: string | null): React.ReactNode {
  if (!iso) return <span className="text-muted-foreground">—</span>
  return new Date(iso).toLocaleString()
}

function truncate(value: string, max: number): string {
  if (value.length <= max) return value
  return value.slice(0, max - 1) + '…'
}

type SubStatus = 'active' | 'inactive' | 'failing'

function statusOf(sub: WebhookSubscription): SubStatus {
  if (!sub.is_active) return 'inactive'
  if (sub.consecutive_failures > 3) return 'failing'
  return 'active'
}

export default function SettingsWebhooksPage() {
  const [subs, setSubs] = useState<WebhookSubscription[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [flashId, setFlashId] = useState<number | null>(null)
  const [pendingId, setPendingId] = useState<number | null>(null)
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [revealedSub, setRevealedSub] = useState<WebhookSubscriptionCreated | null>(null)
  const [editingSub, setEditingSub] = useState<WebhookSubscription | null>(null)
  const [deliveriesSub, setDeliveriesSub] = useState<WebhookSubscription | null>(null)

  const fetchSubs = useCallback(() => {
    setIsLoading(true)
    setError(null)
    webhooksApi
      .list()
      .then((data) => setSubs(data))
      .catch((err) => {
        if (err instanceof ApiError) setError(err.message)
        else setError('Could not load webhooks. Try again.')
      })
      .finally(() => setIsLoading(false))
  }, [])

  useEffect(() => {
    fetchSubs()
  }, [fetchSubs])

  async function handleTest(target: WebhookSubscription) {
    setError(null)
    setPendingId(target.id)
    try {
      await webhooksApi.test(target.id)
      setFlashId(target.id)
      globalThis.setTimeout(() => {
        setFlashId((current) => (current === target.id ? null : current))
      }, 2000)
      setDeliveriesSub(target)
    } catch (err) {
      if (err instanceof ApiError) setError(err.message)
      else setError('Could not fire test event. Try again.')
    } finally {
      setPendingId((current) => (current === target.id ? null : current))
    }
  }

  async function handleToggleActive(target: WebhookSubscription) {
    setError(null)
    setPendingId(target.id)
    const previous = subs
    const nextActive = !target.is_active
    setSubs((prev) =>
      prev.map((s) => (s.id === target.id ? { ...s, is_active: nextActive } : s)),
    )
    try {
      const updated = await webhooksApi.update(target.id, { is_active: nextActive })
      setSubs((prev) => prev.map((s) => (s.id === target.id ? updated : s)))
      setFlashId(target.id)
      globalThis.setTimeout(() => {
        setFlashId((current) => (current === target.id ? null : current))
      }, 2000)
    } catch (err) {
      setSubs(previous)
      if (err instanceof ApiError) setError(err.message)
      else setError('Could not update webhook. Try again.')
      fetchSubs()
    } finally {
      setPendingId((current) => (current === target.id ? null : current))
    }
  }

  async function handleDelete(target: WebhookSubscription) {
    const confirmed = globalThis.confirm(
      `Delete webhook "${target.name}"? Pending deliveries will be cancelled.`,
    )
    if (!confirmed) return
    setError(null)
    setPendingId(target.id)
    const previous = subs
    setSubs((prev) => prev.filter((s) => s.id !== target.id))
    try {
      await webhooksApi.remove(target.id)
    } catch (err) {
      setSubs(previous)
      if (err instanceof ApiError) setError(err.message)
      else setError('Could not delete webhook. Try again.')
      fetchSubs()
    } finally {
      setPendingId((current) => (current === target.id ? null : current))
    }
  }

  function handleCreated(created: WebhookSubscriptionCreated) {
    setIsCreateOpen(false)
    setRevealedSub(created)
    fetchSubs()
  }

  function handleUpdated(updated: WebhookSubscription) {
    setSubs((prev) => prev.map((s) => (s.id === updated.id ? updated : s)))
    setEditingSub(null)
    setFlashId(updated.id)
    globalThis.setTimeout(() => {
      setFlashId((current) => (current === updated.id ? null : current))
    }, 2000)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Webhooks</h2>
          <p className="text-muted-foreground text-sm">
            Deliver Firewatch events to external systems. Each subscription receives a unique
            signing secret used to verify incoming requests.
          </p>
        </div>
        <Button
          type="button"
          onClick={() => setIsCreateOpen(true)}
          className="gap-2"
        >
          <Plus className="h-4 w-4" />
          Create webhook
        </Button>
      </div>

      {error && (
        <Card className="p-4 border-destructive/50">
          <p role="alert" className="text-destructive text-sm">{error}</p>
        </Card>
      )}

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <p className="text-muted-foreground text-sm">Loading webhooks...</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Name</th>
                  <th className="px-4 py-3 text-left font-medium">Target URL</th>
                  <th className="px-4 py-3 text-left font-medium">Events</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3 text-left font-medium">Last delivered</th>
                  <th className="px-4 py-3 text-left font-medium w-56"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {subs.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-10 text-center text-muted-foreground"
                    >
                      No webhooks yet. Create one to start receiving event notifications.
                    </td>
                  </tr>
                ) : (
                  subs.map((s) => {
                    const status = statusOf(s)
                    const isPending = pendingId === s.id
                    const showFlash = flashId === s.id
                    return (
                      <tr key={s.id} className="hover:bg-muted/40 transition-colors">
                        <td className="px-4 py-3 font-medium">{s.name}</td>
                        <td className="px-4 py-3">
                          <span
                            className="font-mono text-xs"
                            title={s.target_url}
                          >
                            {truncate(s.target_url, 48)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            {s.event_types.map((evt) => (
                              <Badge key={evt} variant="outline">{evt}</Badge>
                            ))}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={status} failures={s.consecutive_failures} />
                        </td>
                        <td className="px-4 py-3">{formatDate(s.last_delivered_at)}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => handleTest(s)}
                              disabled={isPending}
                              title="Send test event"
                              aria-label="Send test event"
                            >
                              <Zap className="h-4 w-4" />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => handleToggleActive(s)}
                              disabled={isPending}
                              title={s.is_active ? 'Disable webhook' : 'Enable webhook'}
                              aria-label={s.is_active ? 'Disable webhook' : 'Enable webhook'}
                            >
                              {s.is_active ? (
                                <Eye className="h-4 w-4" />
                              ) : (
                                <EyeOff className="h-4 w-4" />
                              )}
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => setEditingSub(s)}
                              disabled={isPending}
                              title="Edit webhook"
                              aria-label="Edit webhook"
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => setDeliveriesSub(s)}
                              disabled={isPending}
                              title="View deliveries"
                              aria-label="View deliveries"
                            >
                              <History className="h-4 w-4" />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => handleDelete(s)}
                              disabled={isPending}
                              title="Delete webhook"
                              aria-label="Delete webhook"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                            {showFlash && (
                              <Check
                                className="h-4 w-4 text-green-600 ml-1"
                                aria-label="Webhook updated"
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

      <CreateWebhookDialog
        open={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onCreated={handleCreated}
      />

      <EditWebhookDialog
        sub={editingSub}
        onClose={() => setEditingSub(null)}
        onUpdated={handleUpdated}
      />

      <RevealSecretDialog
        created={revealedSub}
        onClose={() => setRevealedSub(null)}
      />

      <DeliveriesDialog
        sub={deliveriesSub}
        onClose={() => setDeliveriesSub(null)}
      />
    </div>
  )
}

interface StatusBadgeProps {
  status: SubStatus
  failures: number
}

function StatusBadge({ status, failures }: Readonly<StatusBadgeProps>) {
  if (status === 'failing') {
    return (
      <Badge variant="destructive" title={`${failures} consecutive failures`}>
        Failing
      </Badge>
    )
  }
  if (status === 'inactive') {
    return <Badge variant="outline">Inactive</Badge>
  }
  return <Badge variant="default">Active</Badge>
}

// -------------------------------------------------------------------------
// Create dialog
// -------------------------------------------------------------------------

interface CreateWebhookDialogProps {
  open: boolean
  onClose: () => void
  onCreated: (created: WebhookSubscriptionCreated) => void
}

function CreateWebhookDialog({ open, onClose, onCreated }: Readonly<CreateWebhookDialogProps>) {
  const [name, setName] = useState('')
  const [targetUrl, setTargetUrl] = useState('')
  const [selectedEvents, setSelectedEvents] = useState<Set<WebhookEventType>>(new Set())
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setName('')
      setTargetUrl('')
      setSelectedEvents(new Set())
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

  function toggleEvent(evt: WebhookEventType) {
    setSelectedEvents((prev) => {
      const next = new Set(prev)
      if (next.has(evt)) next.delete(evt)
      else next.add(evt)
      return next
    })
  }

  const canSubmit =
    !isSubmitting &&
    name.trim().length > 0 &&
    targetUrl.trim().length > 0 &&
    selectedEvents.size > 0 &&
    /^https?:\/\//i.test(targetUrl.trim())

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!canSubmit) return
    setError(null)
    setIsSubmitting(true)
    try {
      const payload: WebhookSubscriptionCreate = {
        name: name.trim(),
        target_url: targetUrl.trim(),
        event_types: Array.from(selectedEvents),
      }
      const created = await webhooksApi.create(payload)
      onCreated(created)
    } catch (err) {
      if (err instanceof ApiError) setError(err.message)
      else setError('Could not create webhook. Try again.')
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
        aria-labelledby="create-webhook-dialog-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="create-webhook-dialog-title" className="text-lg font-semibold">
              Create webhook
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              The signing secret is shown only once after creation. Store it somewhere safe.
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
            <Label htmlFor="create-webhook-name">Name</Label>
            <Input
              id="create-webhook-name"
              type="text"
              required
              maxLength={120}
              autoComplete="off"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isSubmitting}
              placeholder="e.g. SOC Slack channel"
            />
            <p className="text-xs text-muted-foreground">
              A human-readable label. Up to 120 characters.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="create-webhook-url">Target URL</Label>
            <Input
              id="create-webhook-url"
              type="url"
              required
              autoComplete="off"
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
              disabled={isSubmitting}
              placeholder="https://example.com/firewatch/events"
              pattern="https?://.+"
            />
            <p className="text-xs text-muted-foreground">
              HTTPS is strongly recommended. Must start with https:// or http://.
            </p>
          </div>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Event types</legend>
            <p className="text-xs text-muted-foreground -mt-1">
              Select at least one event type to subscribe to.
            </p>
            <div className="space-y-2 pt-1">
              {SUBSCRIBABLE_EVENTS.map((evt) => {
                const checked = selectedEvents.has(evt.value)
                const inputId = `create-webhook-event-${evt.value}`
                return (
                  <div key={evt.value} className="flex items-start gap-2">
                    <input
                      id={inputId}
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleEvent(evt.value)}
                      disabled={isSubmitting}
                      className="h-4 w-4 rounded border-input mt-0.5"
                    />
                    <div className="flex flex-col">
                      <Label htmlFor={inputId} className="font-mono text-xs cursor-pointer">
                        {evt.label}
                      </Label>
                      <span className="text-xs text-muted-foreground">{evt.description}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </fieldset>

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
            <Button type="submit" disabled={!canSubmit}>
              {isSubmitting ? 'Creating…' : 'Create webhook'}
            </Button>
          </div>
        </form>
      </dialog>
    </div>
  )
}

// -------------------------------------------------------------------------
// Edit dialog
// -------------------------------------------------------------------------

interface EditWebhookDialogProps {
  sub: WebhookSubscription | null
  onClose: () => void
  onUpdated: (updated: WebhookSubscription) => void
}

function EditWebhookDialog({ sub, onClose, onUpdated }: Readonly<EditWebhookDialogProps>) {
  const [name, setName] = useState('')
  const [targetUrl, setTargetUrl] = useState('')
  const [selectedEvents, setSelectedEvents] = useState<Set<WebhookEventType>>(new Set())
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isOpen = sub !== null

  useEffect(() => {
    if (sub) {
      setName(sub.name)
      setTargetUrl(sub.target_url)
      setSelectedEvents(new Set(sub.event_types as WebhookEventType[]))
      setError(null)
      setIsSubmitting(false)
    }
  }, [sub])

  useEffect(() => {
    if (!isOpen) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !isSubmitting) onClose()
    }
    globalThis.addEventListener('keydown', onKey)
    return () => globalThis.removeEventListener('keydown', onKey)
  }, [isOpen, isSubmitting, onClose])

  if (!sub) return null

  function toggleEvent(evt: WebhookEventType) {
    setSelectedEvents((prev) => {
      const next = new Set(prev)
      if (next.has(evt)) next.delete(evt)
      else next.add(evt)
      return next
    })
  }

  const canSubmit =
    !isSubmitting &&
    name.trim().length > 0 &&
    targetUrl.trim().length > 0 &&
    selectedEvents.size > 0 &&
    /^https?:\/\//i.test(targetUrl.trim())

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!canSubmit || !sub) return
    setError(null)
    setIsSubmitting(true)
    try {
      const payload: WebhookSubscriptionUpdate = {
        name: name.trim(),
        target_url: targetUrl.trim(),
        event_types: Array.from(selectedEvents),
      }
      const updated = await webhooksApi.update(sub.id, payload)
      onUpdated(updated)
    } catch (err) {
      if (err instanceof ApiError) setError(err.message)
      else setError('Could not update webhook. Try again.')
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
        aria-labelledby="edit-webhook-dialog-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="edit-webhook-dialog-title" className="text-lg font-semibold">
              Edit webhook
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              The signing secret cannot be retrieved or rotated here — delete and recreate
              the webhook if it has been compromised.
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
            <Label htmlFor="edit-webhook-name">Name</Label>
            <Input
              id="edit-webhook-name"
              type="text"
              required
              maxLength={120}
              autoComplete="off"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isSubmitting}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="edit-webhook-url">Target URL</Label>
            <Input
              id="edit-webhook-url"
              type="url"
              required
              autoComplete="off"
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
              disabled={isSubmitting}
              pattern="https?://.+"
            />
          </div>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Event types</legend>
            <div className="space-y-2 pt-1">
              {SUBSCRIBABLE_EVENTS.map((evt) => {
                const checked = selectedEvents.has(evt.value)
                const inputId = `edit-webhook-event-${evt.value}`
                return (
                  <div key={evt.value} className="flex items-start gap-2">
                    <input
                      id={inputId}
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleEvent(evt.value)}
                      disabled={isSubmitting}
                      className="h-4 w-4 rounded border-input mt-0.5"
                    />
                    <div className="flex flex-col">
                      <Label htmlFor={inputId} className="font-mono text-xs cursor-pointer">
                        {evt.label}
                      </Label>
                      <span className="text-xs text-muted-foreground">{evt.description}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </fieldset>

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
            <Button type="submit" disabled={!canSubmit}>
              {isSubmitting ? 'Saving…' : 'Save changes'}
            </Button>
          </div>
        </form>
      </dialog>
    </div>
  )
}

// -------------------------------------------------------------------------
// Reveal secret dialog
// -------------------------------------------------------------------------

interface RevealSecretDialogProps {
  created: WebhookSubscriptionCreated | null
  onClose: () => void
}

function RevealSecretDialog({ created, onClose }: Readonly<RevealSecretDialogProps>) {
  const [copiedSecret, setCopiedSecret] = useState(false)
  const [copiedSnippet, setCopiedSnippet] = useState(false)

  const isOpen = created !== null

  useEffect(() => {
    if (!isOpen) {
      setCopiedSecret(false)
      setCopiedSnippet(false)
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

  async function handleCopySecret() {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.secret)
      setCopiedSecret(true)
      globalThis.setTimeout(() => setCopiedSecret(false), 2000)
    } catch {
      setCopiedSecret(false)
    }
  }

  async function handleCopySnippet() {
    try {
      await navigator.clipboard.writeText(VERIFICATION_SNIPPET)
      setCopiedSnippet(true)
      globalThis.setTimeout(() => setCopiedSnippet(false), 2000)
    } catch {
      setCopiedSnippet(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <dialog
        open
        className="static m-0 w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg"
        aria-modal="true"
        aria-labelledby="reveal-webhook-secret-dialog-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="reveal-webhook-secret-dialog-title" className="text-lg font-semibold">
              Your new webhook secret
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">{created.name}</p>
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
              Copy this secret now — it will not be shown again. If you lose it, you'll need
              to delete this webhook and create a new one.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="reveal-webhook-secret">Signing secret</Label>
            <div className="flex gap-2">
              <Input
                id="reveal-webhook-secret"
                type="text"
                readOnly
                value={created.secret}
                onFocus={(e) => e.currentTarget.select()}
                className="font-mono text-xs"
              />
              <Button
                type="button"
                variant="outline"
                onClick={handleCopySecret}
                className="gap-2 shrink-0"
              >
                <Copy className="h-4 w-4" />
                {copiedSecret ? 'Copied!' : 'Copy'}
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>How to verify deliveries</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleCopySnippet}
                className="gap-2"
              >
                <Copy className="h-3 w-3" />
                {copiedSnippet ? 'Copied!' : 'Copy'}
              </Button>
            </div>
            <pre className="rounded-md border bg-muted/50 p-3 text-xs whitespace-pre-wrap font-mono">
              {VERIFICATION_SNIPPET}
            </pre>
          </div>

          <div className="flex justify-end pt-2">
            <Button type="button" onClick={onClose}>
              I've saved my secret
            </Button>
          </div>
        </div>
      </dialog>
    </div>
  )
}

// -------------------------------------------------------------------------
// Deliveries dialog
// -------------------------------------------------------------------------

interface DeliveriesDialogProps {
  sub: WebhookSubscription | null
  onClose: () => void
}

function DeliveriesDialog({ sub, onClose }: Readonly<DeliveriesDialogProps>) {
  const [items, setItems] = useState<WebhookDelivery[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isOpen = sub !== null
  const subId = sub?.id ?? null

  const fetchDeliveries = useCallback(() => {
    if (subId === null) return
    setIsLoading(true)
    setError(null)
    webhooksApi
      .deliveries(subId, 0, 50)
      .then((data) => {
        setItems(data.items)
        setTotal(data.total)
      })
      .catch((err) => {
        if (err instanceof ApiError) setError(err.message)
        else setError('Could not load deliveries. Try again.')
      })
      .finally(() => setIsLoading(false))
  }, [subId])

  useEffect(() => {
    if (isOpen) fetchDeliveries()
  }, [isOpen, fetchDeliveries])

  useEffect(() => {
    if (!isOpen) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    globalThis.addEventListener('keydown', onKey)
    return () => globalThis.removeEventListener('keydown', onKey)
  }, [isOpen, onClose])

  if (!sub) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <dialog
        open
        className="static m-0 w-full max-w-4xl rounded-lg border bg-background p-6 shadow-lg max-h-[90vh] overflow-hidden flex flex-col"
        aria-modal="true"
        aria-labelledby="webhook-deliveries-dialog-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="webhook-deliveries-dialog-title" className="text-lg font-semibold">
              Recent deliveries
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {sub.name} —{' '}
              <span className="font-mono text-xs">{truncate(sub.target_url, 60)}</span>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={fetchDeliveries}
              disabled={isLoading}
              className="gap-2"
            >
              <RefreshCw className={`h-3 w-3 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <button
              type="button"
              onClick={onClose}
              className="text-muted-foreground hover:text-foreground"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="mt-4 flex-1 overflow-auto">
          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 mb-3">
              <p role="alert" className="text-sm text-destructive">{error}</p>
            </div>
          )}

          {isLoading ? (
            <div className="flex items-center justify-center py-10">
              <p className="text-muted-foreground text-sm">Loading deliveries...</p>
            </div>
          ) : items.length === 0 ? (
            <div className="flex items-center justify-center py-10">
              <p className="text-muted-foreground text-sm">
                No deliveries yet. Fire a test event to populate this list.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">When</th>
                    <th className="px-3 py-2 text-left font-medium">Event</th>
                    <th className="px-3 py-2 text-left font-medium">Status</th>
                    <th className="px-3 py-2 text-left font-medium">HTTP</th>
                    <th className="px-3 py-2 text-left font-medium">Attempts</th>
                    <th className="px-3 py-2 text-left font-medium">Error</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {items.map((d) => (
                    <tr key={d.id}>
                      <td className="px-3 py-2 whitespace-nowrap">{formatDate(d.created_at)}</td>
                      <td className="px-3 py-2 font-mono text-xs">{d.event_type}</td>
                      <td className="px-3 py-2">
                        <DeliveryStatusBadge status={d.status} />
                      </td>
                      <td className="px-3 py-2">
                        {d.http_status ?? <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="px-3 py-2">{d.attempt_count}</td>
                      <td className="px-3 py-2">
                        {d.error ? (
                          <span title={d.error} className="text-destructive text-xs">
                            {truncate(d.error, 80)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!isLoading && total > items.length && (
            <p className="mt-3 text-xs text-muted-foreground">
              Showing {items.length} of {total} deliveries.
            </p>
          )}
        </div>

        <div className="mt-4 flex justify-end pt-2 border-t">
          <Button type="button" variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </dialog>
    </div>
  )
}

interface DeliveryStatusBadgeProps {
  status: string
}

function DeliveryStatusBadge({ status }: Readonly<DeliveryStatusBadgeProps>) {
  if (status === 'success') {
    return <Badge variant="mitigated">success</Badge>
  }
  if (status === 'failed') {
    return <Badge variant="destructive">failed</Badge>
  }
  if (status === 'pending') {
    return <Badge variant="in_progress">pending</Badge>
  }
  return <Badge variant="outline">{status}</Badge>
}

