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
import { CATEGORIES } from '@/lib/constants'
import { currentScore, scoreLabel } from '@/types'
import type { BulkRiskResult, Risk, RiskStatus } from '@/types'
import { Badge, scoreToBadgeVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import ImportRisksDialog from '@/components/risks/ImportRisksDialog'
import BulkReassignDialog from '@/components/risks/BulkReassignDialog'
import BulkStatusDialog from '@/components/risks/BulkStatusDialog'
import BulkRescoreDialog from '@/components/risks/BulkRescoreDialog'
import { ShieldAlert, ArrowUpDown, ArrowUp, ArrowDown, Plus, Download, Upload, X, Search } from 'lucide-react'

// ---- Types ------------------------------------------------------------------

type SortKey = 'id' | 'title' | 'category' | 'score' | 'status' | 'owner' | 'next_review'
type SortDir = 'asc' | 'desc'
type SeverityBucket = 'all' | 'Critical' | 'High' | 'Medium' | 'Low' | 'Unscored'

const SEVERITY_BUCKETS: Exclude<SeverityBucket, 'all'>[] = ['Critical', 'High', 'Medium', 'Low', 'Unscored']

function ownerLabel(risk: Risk): string {
  return risk.owner?.full_name ?? risk.owner?.email ?? `#${risk.owner_id}`
}

function severityBucket(risk: Risk): Exclude<SeverityBucket, 'all'> {
  const s = currentScore(risk)
  if (s === null) return 'Unscored'
  return scoreLabel(s)
}

// ---- Helpers ----------------------------------------------------------------

function bulkBannerMessage(updated: number, failed: number): string {
  const plural = updated === 1 ? '' : 's'
  if (failed > 0) return `Updated ${updated} risk${plural} · ${failed} failed`
  return `Updated ${updated} risk${plural}`
}

/** Display label for each status value. */
const STATUS_LABELS: Record<RiskStatus, string> = {
  open:        'Open',
  in_progress: 'In Progress',
  mitigated:   'Mitigated',
  accepted:    'Accepted',
  closed:      'Closed',
}

type Comparator = (a: Risk, b: Risk) => { result: number; pinToEnd: number }

const COMPARATORS: Record<SortKey, Comparator> = {
  title:       (a, b) => ({ result: a.title.localeCompare(b.title), pinToEnd: 0 }),
  score:       (a, b) => ({ result: (currentScore(a) ?? -1) - (currentScore(b) ?? -1), pinToEnd: 0 }),
  status:      (a, b) => ({ result: a.status.localeCompare(b.status), pinToEnd: 0 }),
  id:          (a, b) => ({ result: a.risk_id.localeCompare(b.risk_id, undefined, { numeric: true }), pinToEnd: 0 }),
  owner:       (a, b) => ({
    result: (a.owner?.full_name ?? a.owner?.email ?? `#${a.owner_id}`)
              .localeCompare(b.owner?.full_name ?? b.owner?.email ?? `#${b.owner_id}`),
    pinToEnd: 0,
  }),
  category:    (a, b) => {
    const ca = a.category ?? ''
    const cb = b.category ?? ''
    if (!ca && cb) return { result: 0, pinToEnd: 1 }
    if (ca && !cb) return { result: 0, pinToEnd: -1 }
    return { result: ca.localeCompare(cb), pinToEnd: 0 }
  },
  next_review: (a, b) => {
    const da = a.next_review_date ?? ''
    const db = b.next_review_date ?? ''
    if (!da && db) return { result: 0, pinToEnd: 1 }
    if (da && !db) return { result: 0, pinToEnd: -1 }
    return { result: da.localeCompare(db), pinToEnd: 0 }
  },
}

/** Sort comparator — returns negative/zero/positive like Array.sort expects. */
function compareRisks(a: Risk, b: Risk, key: SortKey, dir: SortDir): number {
  const { result, pinToEnd } = COMPARATORS[key](a, b)
  if (pinToEnd !== 0) return pinToEnd
  return dir === 'asc' ? result : -result
}

function emptyStateMessage(anyFilterActive: boolean, canCreate: boolean): string {
  if (anyFilterActive) return 'No risks match your filters. Try clearing them.'
  if (canCreate) return 'Get started by creating your first risk.'
  return 'No risks have been logged yet.'
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
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [ownerFilter, setOwnerFilter] = useState<string>('all')
  const [severityFilter, setSeverityFilter] = useState<SeverityBucket>('all')
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
  const [statusOpen, setStatusOpen] = useState(false)
  const [rescoreOpen, setRescoreOpen] = useState(false)
  const [bulkBanner, setBulkBanner] = useState<{ message: string; details: BulkRiskResult['errors'] } | null>(null)
  const bannerTimerRef = useRef<ReturnType<typeof globalThis.setTimeout> | null>(null)

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
  useEffect(() => { setSelected(new Set()) }, [dueForReviewOnly, statusFilter, search, categoryFilter, ownerFilter, severityFilter])

  // Clean up any pending banner-dismiss timer on unmount.
  useEffect(() => () => {
    if (bannerTimerRef.current !== null) globalThis.clearTimeout(bannerTimerRef.current)
  }, [])

  function showBulkBanner(result: BulkRiskResult) {
    const updated = result.updated.length
    const failed = result.errors.length
    const message = bulkBannerMessage(updated, failed)
    setBulkBanner({ message, details: result.errors })
    if (bannerTimerRef.current !== null) globalThis.clearTimeout(bannerTimerRef.current)
    bannerTimerRef.current = globalThis.setTimeout(() => setBulkBanner(null), 5000)
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

  // Distinct owners present in the loaded risks, sorted by label.
  const ownerOptions = useMemo(() => {
    const map = new Map<number, string>()
    for (const r of risks) {
      if (!map.has(r.owner_id)) map.set(r.owner_id, ownerLabel(r))
    }
    return Array.from(map.entries())
      .map(([id, label]) => ({ id, label }))
      .sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }))
  }, [risks])

  // Derived: filtered then sorted — recalculated only when dependencies change.
  // useMemo avoids re-sorting on every render (e.g. while the user types elsewhere).
  const displayedRisks = useMemo(() => {
    let items = risks
    if (statusFilter !== 'all') {
      items = items.filter((r) => r.status === statusFilter)
    }
    if (categoryFilter !== 'all') {
      items = items.filter((r) => r.category === categoryFilter)
    }
    if (ownerFilter !== 'all') {
      const ownerId = Number(ownerFilter)
      items = items.filter((r) => r.owner_id === ownerId)
    }
    if (severityFilter !== 'all') {
      items = items.filter((r) => severityBucket(r) === severityFilter)
    }
    const q = search.trim().toLowerCase()
    if (q) {
      items = items.filter((r) => {
        const fields = [
          r.risk_id,
          r.title,
          r.description ?? '',
          r.threat_source ?? '',
          r.threat_event ?? '',
          r.vulnerability ?? '',
          r.affected_asset ?? '',
          r.category ?? '',
          ownerLabel(r),
        ]
        return fields.some((f) => f.toLowerCase().includes(q))
      })
    }
    return [...items].sort((a, b) => compareRisks(a, b, sortKey, sortDir))
  }, [risks, statusFilter, categoryFilter, ownerFilter, severityFilter, search, sortKey, sortDir])

  const anyFilterActive =
    search.trim() !== '' ||
    statusFilter !== 'all' ||
    categoryFilter !== 'all' ||
    ownerFilter !== 'all' ||
    severityFilter !== 'all' ||
    dueForReviewOnly

  function clearAllFilters() {
    setSearch('')
    setStatusFilter('all')
    setCategoryFilter('all')
    setOwnerFilter('all')
    setSeverityFilter('all')
    setDueForReviewOnly(false)
  }

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
              {bulkBanner.details.slice(0, 5).map((e) => (
                <li key={e.risk_id} className="font-mono">
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
            <Button variant="outline" size="sm" onClick={() => setStatusOpen(true)}>
              Change status…
            </Button>
            <Button variant="outline" size="sm" onClick={() => setRescoreOpen(true)}>
              Log review…
            </Button>
          </div>
        </div>
      )}

      {/* Filter bar */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <div className="relative w-64">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              type="search"
              placeholder="Search risks…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8"
            />
          </div>
          {anyFilterActive && (
            <button
              type="button"
              onClick={clearAllFilters}
              className="ml-auto text-xs text-muted-foreground hover:text-foreground underline"
            >
              Clear filters
            </button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
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

          <label htmlFor="category-filter" className="text-sm font-medium">
            Category
          </label>
          <select
            id="category-filter"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="all">All categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          <label htmlFor="owner-filter" className="text-sm font-medium">
            Owner
          </label>
          <select
            id="owner-filter"
            value={ownerFilter}
            onChange={(e) => setOwnerFilter(e.target.value)}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="all">All owners</option>
            {ownerOptions.map((o) => (
              <option key={o.id} value={String(o.id)}>{o.label}</option>
            ))}
          </select>

          <label htmlFor="severity-filter" className="text-sm font-medium">
            Severity
          </label>
          <select
            id="severity-filter"
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as SeverityBucket)}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="all">All severities</option>
            {SEVERITY_BUCKETS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

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
      </div>

      {/* Empty state */}
      {displayedRisks.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-center">
          <ShieldAlert className="h-10 w-10 text-muted-foreground mb-3" />
          <p className="font-medium">No risks found</p>
          <p className="text-muted-foreground text-sm mt-1">
            {emptyStateMessage(anyFilterActive, canCreate)}
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
                <SortableHeader label="ID"          sortKey="id"          current={sortKey} dir={sortDir} onSort={handleSort} />
                <SortableHeader label="Title"       sortKey="title"       current={sortKey} dir={sortDir} onSort={handleSort} />
                <SortableHeader label="Category"    sortKey="category"    current={sortKey} dir={sortDir} onSort={handleSort} />
                <SortableHeader label="Score"       sortKey="score"       current={sortKey} dir={sortDir} onSort={handleSort} />
                <SortableHeader label="Status"      sortKey="status"      current={sortKey} dir={sortDir} onSort={handleSort} />
                <SortableHeader label="Owner"       sortKey="owner"       current={sortKey} dir={sortDir} onSort={handleSort} />
                <SortableHeader label="Next review" sortKey="next_review" current={sortKey} dir={sortDir} onSort={handleSort} />
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
                      <Badge variant={risk.status}>
                        {STATUS_LABELS[risk.status]}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-xs">
                      {risk.owner?.full_name ?? risk.owner?.email ?? `#${risk.owner_id}`}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      <ReviewDateCell nextReviewDate={risk.next_review_date} status={risk.status} />
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
      <BulkStatusDialog
        open={statusOpen}
        riskIds={Array.from(selected)}
        onClose={() => setStatusOpen(false)}
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

// ---- Sub-components ---------------------------------------------------------

function ReviewDateCell({
  nextReviewDate,
  status,
}: Readonly<{
  nextReviewDate: string | null | undefined
  status: RiskStatus
}>) {
  if (!nextReviewDate) {
    return <span className="text-muted-foreground italic text-xs">—</span>
  }
  const today = new Date().toISOString().split('T')[0]
  const isOverdue =
    nextReviewDate <= today &&
    status !== 'closed' &&
    status !== 'mitigated'
  const formatted = new Date(nextReviewDate).toLocaleDateString()
  return isOverdue ? (
    <Badge variant="destructive">{formatted}</Badge>
  ) : (
    <span className="text-muted-foreground">{formatted}</span>
  )
}

function SortIcon({ isActive, dir }: Readonly<{ isActive: boolean; dir: SortDir }>) {
  if (!isActive) return <ArrowUpDown className="h-3 w-3 text-muted-foreground/50" />
  return dir === 'asc'
    ? <ArrowUp className="h-3 w-3 text-foreground" />
    : <ArrowDown className="h-3 w-3 text-foreground" />
}

/** Clickable table header that shows a sort indicator. */
function SortableHeader({
  label,
  sortKey,
  current,
  dir,
  onSort,
}: Readonly<{
  label: string
  sortKey: SortKey
  current: SortKey
  dir: SortDir
  onSort: (key: SortKey) => void
}>) {
  const isActive = current === sortKey
  return (
    <th className="px-4 py-3 text-left font-medium">
      <button
        onClick={() => onSort(sortKey)}
        className="flex items-center gap-1 hover:text-foreground transition-colors"
      >
        {label}
        <SortIcon isActive={isActive} dir={dir} />
        {isActive && (
          <span className="sr-only">{dir === 'asc' ? 'ascending' : 'descending'}</span>
        )}
      </button>
    </th>
  )
}
