/**
 * Risk list page — the primary working view of the app.
 *
 * Features:
 *   - Fetches one page of risks at a time from GET /api/risks (risksApi.list)
 *   - Filter, search and sort are all sent to the server as query params
 *   - Score badge colour-coded by severity (Low/Medium/High/Critical)
 *   - "New risk" button visible only to admin and security_analyst roles
 *
 * The view (filters, search, sort, page, page size) lives in the URL query
 * string (lib/register-view.ts), so refreshing, sharing a link, or coming back
 * from a risk lands on the same page. Every filter/search/sort change resets
 * to page 1. Search is debounced; a request-sequence ref discards stale
 * responses that resolve out of order.
 */
import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { risksApi, ApiError, errorMessage } from '@/services/api'
import { CATEGORIES, RISK_STATUS_LABELS } from '@/lib/constants'
import { currentScore, scoreLabel } from '@/types'
import type { BulkRiskResult, Risk, RiskSeverityParam, RiskSortKey, RiskStatus } from '@/types'
import { calendarDay, formatCalendarDate, todayLocalISODate } from '@/lib/dates'
import {
  PAGE_SIZES,
  SEVERITY_OPTIONS,
  parseRegisterView,
  registerViewToParams,
  rememberRegisterSearch,
  type RegisterView,
} from '@/lib/register-view'
import { Badge, scoreToBadgeVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import ImportRisksDialog from '@/components/risks/ImportRisksDialog'
import BulkReassignDialog from '@/components/risks/BulkReassignDialog'
import BulkStatusDialog from '@/components/risks/BulkStatusDialog'
import BulkRescoreDialog from '@/components/risks/BulkRescoreDialog'
import { ShieldAlert, ArrowUpDown, ArrowUp, ArrowDown, Plus, Download, Upload, X, Search } from 'lucide-react'

// ---- Types ------------------------------------------------------------------

type SortKey = RiskSortKey
type SortDir = 'asc' | 'desc'

const SEARCH_DEBOUNCE_MS = 300
const NO_SELECTION: ReadonlySet<string> = new Set()

function ownerLabel(risk: Risk): string {
  return risk.owner?.full_name ?? risk.owner?.email ?? `#${risk.owner_id}`
}

// ---- Helpers ----------------------------------------------------------------

function bulkBannerMessage(updated: number, failed: number): string {
  const plural = updated === 1 ? '' : 's'
  if (failed > 0) return `Updated ${updated} risk${plural} · ${failed} failed`
  return `Updated ${updated} risk${plural}`
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

  // Raw data from the API — one page.
  const [risks, setRisks] = useState<Risk[]>([])
  const [total, setTotal] = useState(0)
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false)
  const [isFetching, setIsFetching] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // The applied view comes from the URL. Only the text being typed into the
  // search box is local until it settles.
  const [searchParams, setSearchParams] = useSearchParams()
  const view = useMemo(() => parseRegisterView(searchParams), [searchParams])
  const viewKey = useMemo(() => registerViewToParams(view).toString(), [view])
  const { page: pageIndex, pageSize, sort: sortKey, order: sortDir } = view

  const [searchInput, setSearchInput] = useState(view.search)

  // When the applied search changes from outside the box (Back/Forward, the
  // sidebar link), show it. Keyed on the search alone, so a status change
  // mid-typing doesn't wipe what's in the box.
  const [syncedSearch, setSyncedSearch] = useState(view.search)
  if (syncedSearch !== view.search) {
    setSyncedSearch(view.search)
    if (view.search !== searchInput.trim()) setSearchInput(view.search)
  }

  // Any change other than the page itself goes back to page 1. Replacing the
  // history entry keeps the register at one entry, so Back leaves the register
  // rather than stepping through every filter change.
  const updateView = useCallback((patch: Partial<RegisterView>) => {
    setSearchParams(registerViewToParams({ ...view, page: 0, ...patch }), { replace: true })
  }, [view, setSearchParams])

  useEffect(() => {
    rememberRegisterSearch(viewKey ? `?${viewKey}` : '')
  }, [viewKey])

  // Owner filter options — fetched independently of the current page.
  const [ownerOptions, setOwnerOptions] = useState<{ id: number; label: string }[]>([])

  // CSV import / export UI state
  const [isExporting, setIsExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)

  // Bulk action state — selection keyed by risk_id (RISK-NNN), since that's
  // what the bulk endpoints accept. A selection belongs to the view it was
  // made in, so changing the page, a filter or the sort clears it.
  const [selection, setSelection] = useState<{ viewKey: string; ids: ReadonlySet<string> }>(
    { viewKey, ids: NO_SELECTION },
  )
  const selected = selection.viewKey === viewKey ? selection.ids : NO_SELECTION
  const [reassignOpen, setReassignOpen] = useState(false)
  const [statusOpen, setStatusOpen] = useState(false)
  const [rescoreOpen, setRescoreOpen] = useState(false)
  const [bulkBanner, setBulkBanner] = useState<{ message: string; details: BulkRiskResult['errors'] } | null>(null)
  const bannerTimerRef = useRef<ReturnType<typeof globalThis.setTimeout> | null>(null)

  // Debounce the search box; the settled text goes into the URL. Nothing is
  // scheduled when the trimmed text already matches the applied search (on
  // mount, or after a trailing space), so it can't reset the page for nothing.
  // updateView changes with the view, so a pending search is rescheduled
  // against the latest URL instead of overwriting a newer filter change.
  useEffect(() => {
    const next = searchInput.trim()
    if (next === view.search) return
    const handle = globalThis.setTimeout(() => updateView({ search: next }), SEARCH_DEBOUNCE_MS)
    return () => globalThis.clearTimeout(handle)
  }, [searchInput, view.search, updateView])

  const requestSeq = useRef(0)

  const loadRisks = useCallback(() => {
    const seq = ++requestSeq.current
    setIsFetching(true)
    risksApi.list({
      status: view.status !== 'all' ? view.status : undefined,
      category: view.category !== 'all' ? view.category : undefined,
      owner_id: view.owner !== 'all' ? Number(view.owner) : undefined,
      due_for_review: view.dueForReview ? true : undefined,
      search: view.search || undefined,
      severity: view.severity !== 'all' ? view.severity : undefined,
      sort: view.sort,
      order: view.order,
      skip: view.page * view.pageSize,
      limit: view.pageSize,
    })
      .then((data) => {
        if (seq !== requestSeq.current) return // a newer request has since started
        setRisks(data.items)
        setTotal(data.total)
        setError(null)
        // The page can be past the end: a stale link, or a bulk action that
        // moved rows out of the current filter. Step back to the last page
        // that actually has rows.
        if (data.items.length === 0 && data.total > 0) {
          const lastPage = Math.max(0, Math.ceil(data.total / view.pageSize) - 1)
          if (lastPage !== view.page) updateView({ page: lastPage })
        }
      })
      .catch((err) => {
        if (seq !== requestSeq.current) return
        // 401 means the session expired — prompt to re-login rather than
        // showing a generic error that implies something is broken.
        const message = err instanceof ApiError && err.status === 401
          ? 'Your session has expired. Please sign in again.'
          : 'Could not load risks. Check that the backend is running and try refreshing.'
        setError(message)
      })
      .finally(() => {
        if (seq !== requestSeq.current) return
        setIsFetching(false)
        setHasLoadedOnce(true)
      })
  }, [view, updateView])

  useEffect(() => { loadRisks() }, [loadRisks])

  const loadOwnerOptions = useCallback(() => {
    risksApi.owners()
      .then((owners) => {
        setOwnerOptions(owners.map((o) => ({ id: o.id, label: o.full_name ?? o.email })))
      })
      .catch(() => { /* Owner dropdown just keeps "All owners" on failure. */ })
  }, [])

  useEffect(() => { loadOwnerOptions() }, [loadOwnerOptions])

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

  function setSelected(ids: ReadonlySet<string>) {
    setSelection({ viewKey, ids })
  }

  function handleBulkDone(result: BulkRiskResult) {
    showBulkBanner(result)
    setSelected(NO_SELECTION)
    loadRisks()
    loadOwnerOptions() // a reassign can introduce/remove owners from the filter list
  }

  function handleImported() {
    loadRisks()
    loadOwnerOptions() // an import can introduce new owners
  }

  function toggleSelected(riskId: string) {
    setSelection((prev) => {
      const next = new Set(prev.viewKey === viewKey ? prev.ids : NO_SELECTION)
      if (next.has(riskId)) next.delete(riskId)
      else next.add(riskId)
      return { viewKey, ids: next }
    })
  }

  async function handleExport() {
    setIsExporting(true)
    setExportError(null)
    try {
      await risksApi.exportCsv()
    } catch (err) {
      setExportError(errorMessage(err, 'Could not export, try again.'))
    } finally {
      setIsExporting(false)
    }
  }

  const anyFilterActive =
    searchInput.trim() !== '' ||
    view.status !== 'all' ||
    view.category !== 'all' ||
    view.owner !== 'all' ||
    view.severity !== 'all' ||
    view.dueForReview

  function clearAllFilters() {
    setSearchInput('')
    updateView({ search: '', status: 'all', category: 'all', owner: 'all', severity: 'all', dueForReview: false })
  }

  // Toggle sort: clicking the same column flips direction; new column starts asc.
  function handleSort(key: SortKey) {
    if (key === sortKey) {
      updateView({ order: sortDir === 'asc' ? 'desc' : 'asc' })
    } else {
      updateView({ sort: key, order: 'asc' })
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

  // Select-all checkbox helpers — operate on the current page only.
  const pageIds = useMemo(() => risks.map((r) => r.risk_id), [risks])
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id))
  const somePageSelected = pageIds.some((id) => selected.has(id)) && !allPageSelected

  function toggleSelectAllOnPage() {
    setSelected(allPageSelected ? NO_SELECTION : new Set(pageIds))
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const rangeStart = total === 0 ? 0 : pageIndex * pageSize + 1
  const rangeEnd = Math.min(total, (pageIndex + 1) * pageSize)
  const canGoPrev = pageIndex > 0 && !isFetching
  const canGoNext = pageIndex + 1 < totalPages && !isFetching

  // ---- Render ---------------------------------------------------------------

  // Full-page loading state only on the very first load — later loads keep
  // the header, filter bar and search input mounted (so the search box never
  // loses focus while the user is typing).
  if (!hasLoadedOnce && isFetching) {
    return (
      <div className="flex items-center justify-center h-48">
        <p className="text-muted-foreground text-sm">Loading risks...</p>
      </div>
    )
  }

  if (!hasLoadedOnce && error) {
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
            {total} risk{total === 1 ? '' : 's'} total
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
        onImported={handleImported}
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
        {hasLoadedOnce && error && (
          <p className="text-destructive text-sm">{error}</p>
        )}
        <div className="flex items-center gap-3">
          <div className="relative w-64">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              type="search"
              placeholder="Search risks…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
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
            value={view.status}
            onChange={(e) => updateView({ status: e.target.value as RiskStatus | 'all' })}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="all">All</option>
            {(Object.keys(RISK_STATUS_LABELS) as RiskStatus[]).map((s) => (
              <option key={s} value={s}>{RISK_STATUS_LABELS[s]}</option>
            ))}
          </select>

          <label htmlFor="category-filter" className="text-sm font-medium">
            Category
          </label>
          <select
            id="category-filter"
            value={view.category}
            onChange={(e) => updateView({ category: e.target.value as RegisterView['category'] })}
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
            value={view.owner}
            onChange={(e) => updateView({ owner: e.target.value })}
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
            value={view.severity}
            onChange={(e) => updateView({ severity: e.target.value as RiskSeverityParam | 'all' })}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="all">All severities</option>
            {SEVERITY_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>

          <label htmlFor="due-for-review" className="flex items-center gap-2 text-sm font-medium ml-2">
            <input
              id="due-for-review"
              type="checkbox"
              checked={view.dueForReview}
              onChange={(e) => updateView({ dueForReview: e.target.checked })}
              className="h-4 w-4 rounded border-input text-primary focus:ring-2 focus:ring-ring"
            />
            <span>Due for review only</span>
          </label>
        </div>
      </div>

      {/* Empty state */}
      {total === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-center">
          <ShieldAlert className="h-10 w-10 text-muted-foreground mb-3" />
          <p className="font-medium">No risks found</p>
          <p className="text-muted-foreground text-sm mt-1">
            {emptyStateMessage(anyFilterActive, canCreate)}
          </p>
        </div>
      ) : (
        <>
          {/* Risk table — dimmed and non-interactive while a later load is in flight. */}
          <div
            className={`rounded-lg border overflow-hidden ${isFetching && hasLoadedOnce ? 'opacity-60' : ''}`}
            aria-busy={isFetching}
          >
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  {canEdit && (
                    <th className="px-4 py-3 text-left font-medium w-10">
                      <input
                        type="checkbox"
                        aria-label="Select all risks on this page"
                        checked={allPageSelected}
                        ref={(el) => { if (el) el.indeterminate = somePageSelected }}
                        onChange={toggleSelectAllOnPage}
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
                {risks.map((risk) => {
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
                        {score === null ? (
                          <span className="text-muted-foreground italic text-xs">Unscored</span>
                        ) : (
                          <Badge variant={scoreToBadgeVariant(score)}>
                            {score} — {scoreLabel(score)}
                          </Badge>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={risk.status}>
                          {RISK_STATUS_LABELS[risk.status]}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">
                        {ownerLabel(risk)}
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

          {/* Pager */}
          <div className="flex items-center justify-between text-sm">
            <p className="text-muted-foreground">
              Showing {rangeStart}–{rangeEnd} of {total}
            </p>
            <div className="flex items-center gap-3">
              <label htmlFor="page-size" className="text-muted-foreground">
                Rows per page
              </label>
              <select
                id="page-size"
                value={pageSize}
                onChange={(e) => updateView({ pageSize: Number(e.target.value) })}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {PAGE_SIZES.map((size) => (
                  <option key={size} value={size}>{size}</option>
                ))}
              </select>
              <label htmlFor="page-number" className="text-muted-foreground">
                Page
              </label>
              <select
                id="page-number"
                value={pageIndex + 1}
                onChange={(e) => updateView({ page: Number(e.target.value) - 1 })}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {Array.from({ length: totalPages }, (_, i) => (
                  <option key={i + 1} value={i + 1}>{i + 1}</option>
                ))}
              </select>
              <span className="text-muted-foreground whitespace-nowrap">of {totalPages}</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => updateView({ page: pageIndex - 1 })}
                disabled={!canGoPrev}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => updateView({ page: pageIndex + 1 })}
                disabled={!canGoNext}
              >
                Next
              </Button>
            </div>
          </div>
        </>
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
  const isOverdue =
    calendarDay(nextReviewDate) <= todayLocalISODate() &&
    status !== 'closed' &&
    status !== 'mitigated'
  const formatted = formatCalendarDate(nextReviewDate)
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
