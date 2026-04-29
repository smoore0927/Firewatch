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
import { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { risksApi, ApiError } from '@/services/api'
import { currentScore, scoreLabel } from '@/types'
import type { Risk, RiskStatus } from '@/types'
import { Badge, scoreToBadgeVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ShieldAlert, ArrowUpDown, Plus } from 'lucide-react'

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
  const [sortKey, setSortKey] = useState<SortKey>('title')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  // Fetch on mount
  useEffect(() => {
    risksApi.list()
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
  }, [])

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
        </div>
        {canCreate && (
          <Button onClick={() => navigate('/risks/new')} className="gap-2">
            <Plus className="h-4 w-4" />
            New risk
          </Button>
        )}
      </div>

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
                <th className="px-4 py-3 text-left font-medium w-28">ID</th>

                {/* Sortable column header */}
                <SortableHeader label="Title"  sortKey="title"  current={sortKey} dir={sortDir} onSort={handleSort} />
                <th className="px-4 py-3 text-left font-medium">Category</th>
                <SortableHeader label="Score"  sortKey="score"  current={sortKey} dir={sortDir} onSort={handleSort} />
                <SortableHeader label="Status" sortKey="status" current={sortKey} dir={sortDir} onSort={handleSort} />
                <th className="px-4 py-3 text-left font-medium">Owner</th>
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
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
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
