/**
 * Risk list page — the primary working view of the app.
 *
 * Features:
 *   - Fetches all risks from GET /api/risks on mount
 *   - Client-side filter by status
 *   - Client-side sort by title, score, or status (toggle asc/desc)
 *   - Score badge colour-coded by severity (Low/Medium/High/Critical)
 *   - "New risk" button visible only to admin and security_analyst roles
 *
 * Why client-side sort/filter instead of server-side?
 *   The API supports server-side filtering (status, owner_id) and pagination.
 *   For a small risk register (<500 items) client-side is simpler and instant.
 *   When the register grows, swap the filter/sort state into API query params.
 */
import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { risksApi, ApiError } from '@/services/api'
import { currentScore, scoreLabel } from '@/types'
import type { BulkRiskResult, Risk, RiskStatus } from '@/types'
import { Badge, scoreToBadgeVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import ImportRisksDialog from '@/components/risks/ImportRisksDialog'
import BulkReassignDialog from '@/components/risks/BulkReassignDialog'
import BulkCloseDialog from '@/components/risks/BulkCloseDialog'
import BulkRescoreDialog from '@/components/risks/BulkRescoreDialog'
import { ShieldAlert, ArrowUpDown, Plus, Download, Upload, X } from 'lucide-react'

// ---- Types ------------------------------------------------------------------

type SortKey = 'title' | 'score' | 'status'
type SortDir = 'asc' | 'desc'

// ---- Helpers ----------------------------------------------------------------

/** Display label for each status value. */
const STATUS_LABELS: Record<RiskStatus, string> = {
  open:        'Open',
  in_progress: 'In Progress',
  mitigated:   'Mitigated',
  accepted:    'Accepted',
  closed:      'Closed',
}

/** Sort comparator — returns negative/zero/positive like Array.sort expects. */
function compareRisks(a: Risk, b: Risk, key: SortKey, dir: SortDir): number {
  let result = 0
  if (key === 'title') {
    result = a.title.localeCompare(b.title)
  } else if (key === 'score') {
    const sa = currentScore(a) ?? -1
    const sb = currentScore(b) ?? -1
    result = sa - sb
  } else if (key === 'status') {
    result = a.status.localeCompare(b.status)
  }
  return dir === 'asc' ? result : -result
}

// ---- Component --------------------------------------------------------------

export default function RisksPage() {
  const { user } = useAuth()
  const navigate = useNavigate()

  // Raw data from the API
  const [risks, setRisks] = useState<Risk[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filter + sort state
  const [statusFilter, setStatusFilter] = useState<RiskStatus | 'all'>('all')
  const [dueForReviewOnly, setDueForReviewOnly] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('title')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  // CSV import / export UI state
  const [isExporting, setIsExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)

  // Bulk action state — selection keyed by risk_id (RISK-NNN), since that's
  // what the bulk endpoints accept.
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [reassignOpen, setReassignOpen] = useState(false)
  const [closeOpen, setCloseOpen] = useState(false)
  const [rescoreOpen, setRescoreOpen] = useState(false)
  const [bulkBanner, setBulkBanner] = useState<{ message: string; details: BulkRiskResult['errors'] } | null>(null)
  const bannerTimerRef = useRef<number | null>(null)

  const loadRisks = useCallback(() => {
    setIsLoading(true)
    risksApi.list(dueForReviewOnly ? { due_for_review: true } : undefined)
      .then((data) => {
        setRisks(data.items)
        setTotal(data.total)
      })
      .catch((err) => {
        // 401 means the session expired — prompt to re-login rather than
        // showing a generic error that implies something is broken.
        if (err instanceof ApiError && err.status === 401) {
          setError('Your session has expired. Please sign in again.')
        } else {
          setError('Could not load risks. Check that the backend is running and try refreshing.')
        }
      })
      .finally(() => setIsLoading(false))
  }, [dueForReviewOnly])

  // Re-fetch whenever the due-for-review toggle changes.
  useEffect(() => { loadRisks() }, [loadRisks])

  // Clear selection when the visible set changes underneath the user.
  useEffect(() => { setSelected(new Set()) }, [dueForReviewOnly, statusFilter])

  // Clean up any pending banner-dismiss timer on unmount.
  useEffect(() => () => {
    if (bannerTimerRef.current !== null) window.clearTimeout(bannerTimerRef.current)
  }, [])

  function showBulkBanner(result: BulkRiskResult) {
    const updated = result.updated.length
    const failed = result.errors.length
    const message =
      failed > 0
        ? `Updated ${updated} risk${updated === 1 ? '' : 's'} · ${failed} failed`
        : `Updated ${updated} risk${updated === 1 ? '' : 's'}`
    setBulkBanner({ message, details: result.errors })
    if (bannerTimerRef.current !== null) window.clearTimeout(bannerTimerRef.current)
    bannerTimerRef.current = window.setTimeout(() => setBulkBanner(null), 5000)
  }

  function handleBulkDone(result: BulkRiskResult) {
    showBulkBanner(result)
    setSelected(new Set())
    loadRisks()
  }

  function toggleSelected(riskId: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(riskId)) next.delete(riskId)
      else next.add(riskId)
      return next
    })
  }

  async function handleExport() {
    setIsExporting(true)
    setExportError(null)
    try {
      await risksApi.exportCsv()
    } catch (err) {
      setExportError(err instanceof ApiError ? err.message : 'Could not export, try again.')
    } finally {
      setIsExporting(false)
    }
  }

  // Derived: filtered then sorted — recalculated only when dependencies change.
  // useMemo avoids re-sorting on every render (e.g. while the user types elsewhere).
  const displayedRisks = useMemo(() => {
    let items = risks
    if (statusFilter !== 'all') {
      items = items.filter((r) => r.status === statusFilter)
    }
    return [...items].sort((a, b) => compareRisks(a, b, sortKey, sortDir))
  }, [risks, statusFilter, sortKey, sortDir])

  // Toggle sort: clicking the same column flips direction; new column starts asc.
  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  // Only admin and security_analyst can create risks
  const canCreate =
    user?.role === 'admin' || user?.role === 'security_analyst'

  // Executive viewers can't edit anything. The bulk action bar is hidden for them.
  const canEdit = user?.role !== 'executive_viewer'
  // Reassign requires admin or security_analyst — backend enforces; UI hides.
  const canReassign =
    user?.role === 'admin' || user?.role === 'security_analyst'

  // Select-all checkbox helpers — operate on the currently visible (filtered + sorted) set.
  const visibleIds = useMemo(() => displayedRisks.map((r) => r.risk_id), [displayedRisks])
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selected.has(id))
  const someVisibleSelected = visibleIds.some((id) => selected.has(id)) && !allVisibleSelected

  function toggleSelectAllVisible() {
    if (allVisibleSelected) {
      setSelected(new Set())
    } else {
      setSelected(new Set(visibleIds))
    }
  }

  // ---- Render ---------------------------------------------------------------

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <p className="text-muted-foreground text-sm">Loading risks...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-48">
        <p className="text-destructive text-sm">{error}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">

      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Risk Register</h1>
          <p className="text-muted-foreground text-sm">
            {total} risk{total !== 1 ? 's' : ''} total
          </p>
          {exportError && (
            <p className="text-destructive text-xs mt-1">{exportError}</p>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={handleExport}
            disabled={isExporting}
            className="gap-2"
          >
            <Download className="h-4 w-4" />
            {isExporting ? 'Exporting…' : 'Export CSV'}
          </Button>
          {canCreate && (
            <Button
              variant="outline"
              onClick={() => setImportOpen(true)}
              className="gap-2"
            >
              <Upload className="h-4 w-4" />
              Import CSV
            </Button>
          )}
          {canCreate && (
            <Button onClick={() => navigate('/risks/new')} className="gap-2">
              <Plus className="h-4 w-4" />
              New risk
            </Button>
          )}
        </div>
      </div>

      <ImportRisksDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={loadRisks}
      />

      {/* Bulk action banner — shown after a bulk action completes. */}
      {bulkBanner && (
        <div className="rounded-md border bg-muted/40 px-4 py-3">
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm font-medium">{bulkBanner.message}</p>
            <button
              type="button"
              onClick={() => setBulkBanner(null)}
              className="text-muted-foreground hover:text-foreground"
              aria-label="Dismiss"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          {bulkBanner.details.length > 0 && (
            <ul className="mt-2 max-h-24 overflow-y-auto text-xs text-muted-foreground space-y-0.5">
              {bulkBanner.details.slice(0, 5).map((e, i) => (
                <li key={`${e.risk_id}-${i}`} className="font-mono">
                  {e.risk_id}: {e.message}
                </li>
              ))}
              {bulkBanner.details.length > 5 && (
                <li className="italic">…and {bulkBanner.details.length - 5} more</li>
              )}
            </ul>
          )}
        </div>
      )}

      {/* Bulk action bar — visible only when at least one risk is selected. */}
      {canEdit && selected.size > 0 && (
        <div className="flex items-center justify-between rounded-md border bg-accent/40 px-4 py-2">
          <div className="flex items-center gap-3 text-sm">
            <span className="font-medium">{selected.size} selected</span>
            <button
              type="button"
              onClick={() => setSelected(new Set())}
              className="text-xs text-muted-foreground hover:text-foreground underline"
            >
              Clear
            </button>
          </div>
          <div className="flex gap-2">
            {canReassign && (
              <Button variant="outline" size="sm" onClick={() => setReassignOpen(true)}>
                Reassign owner…
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={() => setCloseOpen(true)}>
              Close…
            </Button>
            <Button variant="outline" size="sm" onClick={() => setRescoreOpen(true)}>
              Re-score…
            </Button>
          </div>
        </div>
      )}

      {/* Filter bar */}
      <div className="flex items-center gap-3">
        <label htmlFor="status-filter" className="text-sm font-medium">
          Status
        </label>
        <select
          id="status-filter"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as RiskStatus | 'all')}
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="all">All</option>
          {(Object.keys(STATUS_LABELS) as RiskStatus[]).map((s) => (
            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
          ))}
        </select>
        {statusFilter !== 'all' && (
          <button
            onClick={() => setStatusFilter('all')}
            className="text-xs text-muted-foreground hover:text-foreground underline"
          >
            Clear
          </button>
        )}

        <label htmlFor="due-for-review" className="flex items-center gap-2 text-sm font-medium ml-2">
          <input
            id="due-for-review"
            type="checkbox"
            checked={dueForReviewOnly}
            onChange={(e) => setDueForReviewOnly(e.target.checked)}
            className="h-4 w-4 rounded border-input text-primary focus:ring-2 focus:ring-ring"
          />
          Due for review only
        </label>
      </div>

      {/* Empty state */}
      {displayedRisks.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-center">
          <ShieldAlert className="h-10 w-10 text-muted-foreground mb-3" />
          <p className="font-medium">No risks found</p>
          <p className="text-muted-foreground text-sm mt-1">
            {statusFilter !== 'all'
              ? 'Try changing the status filter.'
              : canCreate
              ? 'Get started by creating your first risk.'
              : 'No risks have been logged yet.'}
          </p>
        </div>
      ) : (

        /* Risk table */
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                {canEdit && (
                  <th className="px-4 py-3 text-left font-medium w-10">
                    <input
                      type="checkbox"
                      aria-label="Select all visible risks"
                      checked={allVisibleSelected}
                      ref={(el) => { if (el) el.indeterminate = someVisibleSelected }}
                      onChange={toggleSelectAllVisible}
                      className="h-4 w-4 rounded border-input text-primary focus:ring-2 focus:ring-ring"
                    />
                  </th>
                )}
                <th className="px-4 py-3 text-left font-medium w-28">ID</th>

                {/* Sortable column header */}
                <SortableHeader label="Title"  sortKey="title"  current={sortKey} dir={sortDir} onSort={handleSort} />
                <th className="px-4 py-3 text-left font-medium">Category</th>
                <SortableHeader label="Score"  sortKey="score"  current={sortKey} dir={sortDir} onSort={handleSort} />
                <SortableHeader label="Status" sortKey="status" current={sortKey} dir={sortDir} onSort={handleSort} />
                <th className="px-4 py-3 text-left font-medium">Owner</th>
                <th className="px-4 py-3 text-left font-medium">Next review</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {displayedRisks.map((risk) => {
                const score = currentScore(risk)
                return (
                  <tr
                    key={risk.id}
                    onClick={() => navigate(`/risks/${risk.risk_id}`)}
                    className="cursor-pointer hover:bg-muted/40 transition-colors"
                  >
                    {canEdit && (
                      <td
                        className="px-4 py-3"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          aria-label={`Select ${risk.risk_id}`}
                          checked={selected.has(risk.risk_id)}
                          onChange={() => toggleSelected(risk.risk_id)}
                          className="h-4 w-4 rounded border-input text-primary focus:ring-2 focus:ring-ring"
                        />
                      </td>
                    )}
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                      {risk.risk_id}
                    </td>
                    <td className="px-4 py-3 font-medium">{risk.title}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {risk.category ?? <span className="italic">Uncategorised</span>}
                    </td>
                    <td className="px-4 py-3">
                      {score !== null ? (
                        <Badge variant={scoreToBadgeVariant(score)}>
                          {score} — {scoreLabel(score)}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground italic text-xs">Unscored</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={risk.status as any}>
                        {STATUS_LABELS[risk.status]}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-xs">
                      {risk.owner?.full_name ?? risk.owner?.email ?? `#${risk.owner_id}`}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {risk.next_review_date ? (
                        (() => {
                          const today = new Date().toISOString().split('T')[0]
                          const isOverdue =
                            risk.next_review_date <= today &&
                            risk.status !== 'closed' &&
                            risk.status !== 'mitigated'
                          const formatted = new Date(risk.next_review_date).toLocaleDateString()
                          return isOverdue ? (
                            <Badge variant="destructive">{formatted}</Badge>
                          ) : (
                            <span className="text-muted-foreground">{formatted}</span>
                          )
                        })()
                      ) : (
                        <span className="text-muted-foreground italic text-xs">—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <BulkReassignDialog
        open={reassignOpen}
        riskIds={Array.from(selected)}
        onClose={() => setReassignOpen(false)}
        onDone={handleBulkDone}
      />
      <BulkCloseDialog
        open={closeOpen}
        riskIds={Array.from(selected)}
        onClose={() => setCloseOpen(false)}
        onDone={handleBulkDone}
      />
      <BulkRescoreDialog
        open={rescoreOpen}
        riskIds={Array.from(selected)}
        onClose={() => setRescoreOpen(false)}
        onDone={handleBulkDone}
      />
    </div>
  )
}

// ---- Sub-component ----------------------------------------------------------

/** Clickable table header that shows a sort indicator. */
function SortableHeader({
  label,
  sortKey,
  current,
  dir,
  onSort,
}: {
  label: string
  sortKey: SortKey
  current: SortKey
  dir: SortDir
  onSort: (key: SortKey) => void
}) {
  const isActive = current === sortKey
  return (
    <th className="px-4 py-3 text-left font-medium">
      <button
        onClick={() => onSort(sortKey)}
        className="flex items-center gap-1 hover:text-foreground transition-colors"
      >
        {label}
        <ArrowUpDown
          className={`h-3 w-3 ${isActive ? 'text-foreground' : 'text-muted-foreground/50'}`}
        />
        {isActive && (
          <span className="sr-only">{dir === 'asc' ? 'ascending' : 'descending'}</span>
        )}
      </button>
    </th>
  )
}
