/**
 * AuditLogPanel — admin surface for the /api/audit/logs endpoint.
 *
 * Filters: action (free text), resource_type (select), lookback preset (with optional custom datetime range).
 * The backend matches `action` and `resource_type` exactly (no substring),
 * so we just pass the values through.
 *
 * Pagination is server-side via skip/limit; limit is fixed at 50 here.
 *
 * The `details` column holds an opaque, JSON-encoded string written by the
 * backend. We try to parse it for pretty-printing, but fall back to the raw
 * string if it isn't valid JSON. Rendered through React text nodes only —
 * never via dangerouslySetInnerHTML.
 */
import { Fragment, useCallback, useEffect, useState, type ReactNode } from 'react'
import { auditApi, ApiError } from '@/services/api'
import type { AuditLog } from '@/types'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { SearchableSelect } from '@/components/ui/searchable-select'

const PAGE_SIZE = 50

const RESOURCE_TYPES = ['', 'risk', 'user', 'auth'] as const

const LOOKBACK_VALUES = ['all', '1d', '7d', '14d', '30d', 'custom'] as const

type LookbackValue = typeof LOOKBACK_VALUES[number]

const LOOKBACK_LABELS: Record<LookbackValue, string> = {
  all: 'All time',
  '1d': 'Last 24 hours',
  '7d': 'Last 7 days',
  '14d': 'Last 14 days',
  '30d': 'Last 30 days',
  custom: 'Custom range',
}

function lookbackToRange(value: LookbackValue): { start?: string; end?: string } {
  if (value === 'all' || value === 'custom') return {}
  const days = { '1d': 1, '7d': 7, '14d': 14, '30d': 30 }[value]
  const now = new Date()
  return {
    start: new Date(now.getTime() - days * 86_400_000).toISOString(),
    end: now.toISOString(),
  }
}

function actionBadgeClass(action: string): string {
  const segment = action.split('.')[0]
  switch (segment) {
    case 'auth': return 'bg-blue-100 text-blue-800'
    case 'risk': return 'bg-amber-100 text-amber-800'
    case 'user': return 'bg-purple-100 text-purple-800'
    default:     return 'bg-gray-100 text-gray-700'
  }
}

function formatDetails(raw: string | null): string {
  if (raw === null || raw === '') return ''
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}

function toIsoOrUndefined(value: string): string | undefined {
  if (!value) return undefined
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return undefined
  return d.toISOString()
}

export default function AuditLogPanel() {
  const [items, setItems] = useState<AuditLog[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(0)

  // Filter input state — pending values that only apply on "Apply".
  const [actionInput, setActionInput] = useState('')
  const [resourceTypeInput, setResourceTypeInput] = useState('')
  const [lookback, setLookback] = useState<LookbackValue>('7d')
  const [startInput, setStartInput] = useState('')
  const [endInput, setEndInput] = useState('')

  // Filters actually committed to the API call.
  const [appliedFilters, setAppliedFilters] = useState<{
    action?: string
    resource_type?: string
    start?: string
    end?: string
  }>(() => lookbackToRange('7d'))

  // Row expansion state — keyed by audit log id.
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})

  // Available action strings for the searchable dropdown.
  const [actionOptions, setActionOptions] = useState<string[]>([])

  const fetchLogs = useCallback(() => {
    setIsLoading(true)
    setError(null)
    auditApi.list({
      ...appliedFilters,
      skip: page * PAGE_SIZE,
      limit: PAGE_SIZE,
    })
      .then((data) => {
        setItems(data.items)
        setTotal(data.total)
        // Refresh the action dropdown so newly recorded actions appear without a reload.
        // Failures here must not surface as a fetch error.
        auditApi.listActions()
          .then((res) => setActionOptions(res.actions))
          .catch(() => { /* ignore */ })
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) {
          setError('You do not have permission to view audit logs.')
        } else if (err instanceof ApiError) {
          setError(err.message)
        } else {
          setError('Could not load audit logs. Try again.')
        }
      })
      .finally(() => setIsLoading(false))
  }, [appliedFilters, page])

  useEffect(() => { fetchLogs() }, [fetchLogs])

  useEffect(() => {
    auditApi.listActions()
      .then((res) => setActionOptions(res.actions))
      .catch(() => { /* leave empty; dropdown still works */ })
  }, [])

  function handleApply() {
    const range = lookback === 'custom'
      ? { start: toIsoOrUndefined(startInput), end: toIsoOrUndefined(endInput) }
      : lookbackToRange(lookback)
    setAppliedFilters({
      action: actionInput.trim() || undefined,
      resource_type: resourceTypeInput || undefined,
      ...range,
    })
    setPage(0)
  }

  function handleClear() {
    setActionInput('')
    setResourceTypeInput('')
    setStartInput('')
    setEndInput('')
    setLookback('7d')
    setAppliedFilters({ ...lookbackToRange('7d') })
    setPage(0)
  }

  function toggleRow(id: number) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  const startIdx = total === 0 ? 0 : page * PAGE_SIZE + 1
  const endIdx = Math.min((page + 1) * PAGE_SIZE, total)
  const isPrevDisabled = page === 0
  const isNextDisabled = (page + 1) * PAGE_SIZE >= total

  // Decide which body to render — extracted into a variable so the JSX
  // tree below stays free of nested ternaries.
  let body: ReactNode
  if (isLoading) {
    body = (
      <div className="flex items-center justify-center py-16">
        <p className="text-muted-foreground text-sm">Loading...</p>
      </div>
    )
  } else if (items.length === 0) {
    body = (
      <div className="flex items-center justify-center py-16">
        <p className="text-muted-foreground text-sm">No audit events recorded yet.</p>
      </div>
    )
  } else {
    body = (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr>
              <th className="px-4 py-3 text-left font-medium whitespace-nowrap">Time</th>
              <th className="px-4 py-3 text-left font-medium">User</th>
              <th className="px-4 py-3 text-left font-medium">Action</th>
              <th className="px-4 py-3 text-left font-medium">Resource</th>
              <th className="px-4 py-3 text-left font-medium">IP</th>
              <th className="px-4 py-3 text-left font-medium w-24">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map((log) => {
              const resource = log.resource_type
                ? `${log.resource_type}:${log.resource_id ?? ''}`
                : null
              const isOpen = !!expanded[log.id]
              const pretty = isOpen ? formatDetails(log.details) : ''
              return (
                <Fragment key={log.id}>
                  <tr className="hover:bg-muted/40 transition-colors">
                    <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {log.user_email ?? <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <Badge className={actionBadgeClass(log.action)}>
                        {log.action}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-xs font-mono">
                      {resource ?? <span className="text-muted-foreground font-sans">—</span>}
                    </td>
                    <td className="px-4 py-3 text-xs font-mono text-muted-foreground">
                      {log.ip_address ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      {log.details ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => toggleRow(log.id)}
                        >
                          {isOpen ? 'Hide' : 'View'}
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                  {isOpen && log.details && (
                    <tr className="bg-muted/20">
                      <td colSpan={6} className="px-4 py-3">
                        <pre className="text-xs whitespace-pre-wrap break-words font-mono text-foreground">
                          {pretty}
                        </pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="space-y-4">

      {/* Filters */}
      <Card className="p-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="audit-action">Action</Label>
            <SearchableSelect
              id="audit-action"
              value={actionInput}
              onChange={setActionInput}
              options={actionOptions}
              placeholder="(any)"
              emptyText="No matching actions"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="audit-resource-type">Resource type</Label>
            <select
              id="audit-resource-type"
              value={resourceTypeInput}
              onChange={(e) => setResourceTypeInput(e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {RESOURCE_TYPES.map((rt) => (
                <option key={rt} value={rt}>{rt === '' ? '(any)' : rt}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="audit-lookback">Look back</Label>
            <select
              id="audit-lookback"
              value={lookback}
              onChange={(e) => setLookback(e.target.value as LookbackValue)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {LOOKBACK_VALUES.map((v) => (
                <option key={v} value={v}>{LOOKBACK_LABELS[v]}</option>
              ))}
            </select>
          </div>
        </div>

        {lookback === 'custom' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="audit-start">Start</Label>
              <Input
                id="audit-start"
                type="datetime-local"
                value={startInput}
                onChange={(e) => setStartInput(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="audit-end">End</Label>
              <Input
                id="audit-end"
                type="datetime-local"
                value={endInput}
                onChange={(e) => setEndInput(e.target.value)}
              />
            </div>
          </div>
        )}

        <div className="flex items-center gap-2">
          <Button onClick={handleApply}>Apply</Button>
          <Button variant="outline" onClick={handleClear}>Clear</Button>
        </div>
      </Card>

      {/* Results */}
      {error ? (
        <Card className="p-6 border-destructive/50">
          <p className="text-destructive text-sm">{error}</p>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          {body}

          {/* Pagination */}
          {!isLoading && items.length > 0 && (
            <div className="flex items-center justify-between px-4 py-3 border-t bg-muted/20">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={isPrevDisabled}
              >
                Prev
              </Button>
              <p className="text-xs text-muted-foreground">
                Showing {startIdx}–{endIdx} of {total}
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => p + 1)}
                disabled={isNextDisabled}
              >
                Next
              </Button>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
