/**
 * Risk detail view — full record for a single risk.
 *
 * Sections:
 *   1. Header       — risk_id, title, status badge, edit button
 *   2. Score card   — current score, severity, likelihood, impact
 *   3. Details      — category, asset, threat source/event, vulnerability, description
 *   4. Activity     — merged timeline: score changes + status changes (grouped by commit)
 *   5. Edit History — every commit with full field-level before/after, collapsible
 *   6. Treatments   — mitigation plans
 */
import { useEffect, useState, useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { risksApi, usersApi } from '@/services/api'
import { currentScore, scoreLabel } from '@/types'
import type { Risk, RiskAssessment, RiskHistory, RiskStatus, User } from '@/types'
import { Badge, scoreToBadgeVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ArrowLeft, Pencil, ArrowUp, ArrowDown, Minus, RefreshCw, ChevronDown, ChevronRight, X } from 'lucide-react'

// ---- Constants --------------------------------------------------------------

const STATUS_LABELS: Record<RiskStatus, string> = {
  open:        'Open',
  in_progress: 'In Progress',
  mitigated:   'Mitigated',
  accepted:    'Accepted',
  closed:      'Closed',
}

// Mirrors the badge variant classes so the inline status select inherits the
// same colour as the badge it replaces.
const STATUS_COLORS: Record<RiskStatus, string> = {
  open:        'bg-blue-100  text-blue-800',
  in_progress: 'bg-purple-100 text-purple-800',
  mitigated:   'bg-green-100 text-green-800',
  accepted:    'bg-gray-100  text-gray-700',
  closed:      'bg-gray-200  text-gray-500',
}

const LIKELIHOOD_LABELS: Record<number, string> = {
  1: 'Very Low', 2: 'Low', 3: 'Moderate', 4: 'High', 5: 'Very High',
}

// Human-readable labels for field names stored in risk_history.
const FIELD_LABELS: Record<string, string> = {
  title:          'Title',
  description:    'Description',
  threat_source:  'Threat source',
  threat_event:   'Threat event',
  vulnerability:  'Vulnerability',
  affected_asset: 'Affected asset',
  category:       'Category',
  status:         'Status',
  owner_id:       'Owner',
}

// ---- Timeline ---------------------------------------------------------------
// Every visible event — score changes, status changes, and field edits — is
// modelled as a single CommitBatch. When Postgres writes an assessment and
// history rows in the same transaction they share an identical timestamp and
// are merged into one entry. Assessment-only events (from the inline re-assess
// form) become their own single-entry batch.
//
// This gives one unified Activity list instead of two separate visual tracks.

type CommitBatch = {
  date:         string
  statusChange: RiskHistory | null    // status row from this commit, if any
  otherFields:  string[]              // human-readable names of other changed fields
  assessment:   RiskAssessment | null // score change in this commit, if any
  prevScore:    number | null         // score before this commit (drives the arrow)
  statusAtTime: RiskStatus            // status after all changes in this commit
}

// Only one entry kind now — everything is a batch.
type TimelineEntry = { kind: 'batch'; date: string; batch: CommitBatch }

function groupByCommit(rows: RiskHistory[]): Map<string, RiskHistory[]> {
  // PostgreSQL's now() returns the transaction start time, so all rows written
  // in the same db.commit() share an identical changed_at value.
  const map = new Map<string, RiskHistory[]>()
  for (const row of rows) {
    if (!map.has(row.changed_at)) map.set(row.changed_at, [])
    map.get(row.changed_at)!.push(row)
  }
  return map
}

function buildTimeline(risk: Risk): TimelineEntry[] {
  // Index assessments by their assessed_at timestamp for O(1) merge lookup.
  // When an assessment shares a timestamp with history rows (same db.commit),
  // they are merged into one batch entry automatically.
  const assessmentByDate = new Map<string, RiskAssessment>()
  for (const a of risk.assessments) {
    assessmentByDate.set(a.assessed_at, a)
  }

  const historyByDate = groupByCommit(risk.history)

  // Union of all dates across both sources.
  const allDates = new Set([...historyByDate.keys(), ...assessmentByDate.keys()])

  // Walk oldest → newest to maintain running state.
  const sorted = [...allDates].sort((a, b) =>
    new Date(a).getTime() - new Date(b).getTime()
  )

  let currentStatus: RiskStatus = 'open'
  let prevScore: number | null = null
  const entries: TimelineEntry[] = []

  for (const date of sorted) {
    const rows       = historyByDate.get(date) ?? []
    const assessment = assessmentByDate.get(date) ?? null

    const statusRow  = rows.find((r) => r.field_changed === 'status') ?? null
    const otherFields = rows
      .filter((r) => r.field_changed !== 'status')
      .map((r) => FIELD_LABELS[r.field_changed] ?? r.field_changed)

    // Status after this commit: prefer the new status from this batch, else carry forward.
    const statusAtTime = (statusRow?.new_value as RiskStatus) ?? currentStatus

    entries.push({
      kind: 'batch',
      date,
      batch: { date, statusChange: statusRow, otherFields, assessment, prevScore, statusAtTime },
    })

    // Advance running state for the next iteration.
    if (statusRow?.new_value) currentStatus = statusRow.new_value as RiskStatus
    if (assessment)           prevScore = assessment.risk_score
  }

  return entries.reverse() // newest first for display
}

// Build grouped edit history (all fields, full values) for the Edit History section.
type EditCommit = {
  date: string
  changes: RiskHistory[]
}

function buildEditHistory(history: RiskHistory[]): EditCommit[] {
  const commits: EditCommit[] = []
  for (const [date, rows] of groupByCommit(history)) {
    commits.push({ date, changes: rows })
  }
  return commits.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
}

function truncate(value: string | null | undefined, max = 80): string {
  if (!value) return ''
  return value.length > max ? value.slice(0, max) + '...' : value
}

// ---- Sub-components ---------------------------------------------------------

function ScoreArrow({ score, prevScore }: { score: number; prevScore: number | null }) {
  if (prevScore === null) return <Minus className="h-4 w-4 text-muted-foreground" />
  if (score > prevScore)  return <ArrowUp className="h-4 w-4 text-destructive" />
  if (score < prevScore)  return <ArrowDown className="h-4 w-4 text-green-600" />
  return <Minus className="h-4 w-4 text-muted-foreground" />
}

function Detail({ label, value, className }: {
  label: string; value: string | null | undefined; className?: string
}) {
  return (
    <div className={className}>
      <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</dt>
      <dd className="mt-1 text-sm">
        {value ?? <span className="italic text-muted-foreground">Not set</span>}
      </dd>
    </div>
  )
}

// ---- Component --------------------------------------------------------------

export default function RiskDetailPage() {
  const { riskId } = useParams<{ riskId: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()

  const [risk, setRisk] = useState<Risk | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Extracted so handlers (status change, re-assess) can refresh after saving
  // without navigating away.
  function loadRisk() {
    if (!riskId) return
    risksApi.get(riskId).then(setRisk).catch(() => setError('Risk not found.'))
  }

  useEffect(() => {
    if (!riskId) return
    risksApi.get(riskId)
      .then(setRisk)
      .catch(() => setError('Risk not found or you do not have permission to view it.'))
      .finally(() => setIsLoading(false))
  }, [riskId])

  const canEdit =
    user?.role === 'admin' ||
    user?.role === 'security_analyst' ||
    (user?.role === 'risk_owner' && risk?.owner_id === user?.id)

  const timeline    = useMemo(() => risk ? buildTimeline(risk)    : [], [risk])
  const editHistory = useMemo(() => risk ? buildEditHistory(risk.history) : [], [risk])

  const [timelineExpanded, setTimelineExpanded] = useState(false)
  const [expandedCommits, setExpandedCommits]   = useState<Set<string>>(new Set())
  const [selectedChange, setSelectedChange]     = useState<RiskHistory | null>(null)
  const TIMELINE_PREVIEW = 3

  // ---- Assignable users (for owner picker) ----
  // Fetched once on mount. Will silently stay empty for roles that can't assign
  // owners (the endpoint returns 403, which we swallow). The owner field falls
  // back to read-only display when the list is empty.
  const [users, setUsers] = useState<User[]>([])

  useEffect(() => {
    usersApi.listAssignable()
      .then(setUsers)
      .catch(() => {}) // 403 for non-editors — read-only fallback is fine
  }, [])

  // ---- Inline status change ----
  const [isSavingStatus, setIsSavingStatus] = useState(false)

  async function handleStatusChange(e: React.ChangeEvent<HTMLSelectElement>) {
    if (!riskId) return
    setIsSavingStatus(true)
    try {
      await risksApi.update(riskId, { status: e.target.value as RiskStatus })
      loadRisk()
    } finally {
      setIsSavingStatus(false)
    }
  }

  // ---- Inline owner change ----
  const [isSavingOwner, setIsSavingOwner] = useState(false)

  async function handleOwnerChange(e: React.ChangeEvent<HTMLSelectElement>) {
    if (!riskId) return
    setIsSavingOwner(true)
    try {
      await risksApi.update(riskId, { owner_id: Number(e.target.value) })
      loadRisk()
    } finally {
      setIsSavingOwner(false)
    }
  }

  // ---- Inline re-assess ----
  const [isAssessing, setIsAssessing]         = useState(false)
  const [isSavingAssessment, setIsSavingAssessment] = useState(false)
  const [assessForm, setAssessForm] = useState({ likelihood: '', impact: '', notes: '' })

  async function handleAddAssessment(e: React.FormEvent) {
    e.preventDefault()
    if (!riskId || !assessForm.likelihood || !assessForm.impact) return
    setIsSavingAssessment(true)
    try {
      await risksApi.addAssessment(riskId, {
        likelihood: Number(assessForm.likelihood),
        impact:     Number(assessForm.impact),
        ...(assessForm.notes.trim() && { notes: assessForm.notes.trim() }),
      })
      setIsAssessing(false)
      setAssessForm({ likelihood: '', impact: '', notes: '' })
      loadRisk()
    } finally {
      setIsSavingAssessment(false)
    }
  }

  function toggleCommit(date: string) {
    setExpandedCommits((prev) => {
      const next = new Set(prev)
      next.has(date) ? next.delete(date) : next.add(date)
      return next
    })
  }

  // ---- Render ---------------------------------------------------------------

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <p className="text-muted-foreground text-sm">Loading...</p>
      </div>
    )
  }

  if (error || !risk) {
    return (
      <div className="flex items-center justify-center h-48">
        <p className="text-destructive text-sm">{error ?? 'Risk not found.'}</p>
      </div>
    )
  }

  const score = currentScore(risk)
  const latestAssessment = risk.assessments[0] ?? null

  return (
    <>
    <div className="max-w-3xl space-y-8">

      {/* ---- Header ---- */}
      <div>
        <button
          onClick={() => navigate('/risks')}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
        >
          <ArrowLeft className="h-4 w-4" /> Risk Register
        </button>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-mono text-muted-foreground mb-1">{risk.risk_id}</p>
            <h1 className="text-2xl font-bold tracking-tight">{risk.title}</h1>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {canEdit ? (
              // Two-layer approach:
              //   1. Visual layer  — the label + chevron, sized by the text so the
              //      badge width always matches the selected status length.
              //   2. Interaction layer — an invisible <select> with absolute inset-0
              //      so clicking anywhere on the badge opens the dropdown, not just
              //      the text portion.
              <div className={`relative inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium gap-1 ${STATUS_COLORS[risk.status]} ${isSavingStatus ? 'opacity-50' : ''}`}>
                <span>{STATUS_LABELS[risk.status]}</span>
                <ChevronDown className="h-3 w-3 shrink-0 opacity-60" />
                <select
                  value={risk.status}
                  onChange={handleStatusChange}
                  disabled={isSavingStatus}
                  aria-label="Change status"
                  className="absolute inset-0 w-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
                >
                  {(Object.keys(STATUS_LABELS) as RiskStatus[]).map((s) => (
                    <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                  ))}
                </select>
              </div>
            ) : (
              <Badge variant={risk.status as any}>{STATUS_LABELS[risk.status]}</Badge>
            )}
            {canEdit && (
              <Button size="sm" variant="outline" className="gap-2"
                onClick={() => navigate(`/risks/${risk.risk_id}/edit`)}>
                <Pencil className="h-3 w-3" /> Edit
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* ---- Score card ---- */}
      <div className="rounded-lg border p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-4">
          Current Score
        </h2>
        {score !== null ? (
          <div className="flex items-center gap-6">
            <div className="text-center">
              <p className="text-4xl font-bold">{score}</p>
              <p className="text-xs text-muted-foreground mt-1">out of 25</p>
            </div>
            <div className="space-y-1">
              <Badge variant={scoreToBadgeVariant(score)} className="text-sm px-3 py-1">
                {scoreLabel(score)}
              </Badge>
              {latestAssessment && (
                <p className="text-xs text-muted-foreground">
                  Likelihood: <span className="font-medium">{latestAssessment.likelihood} — {LIKELIHOOD_LABELS[latestAssessment.likelihood]}</span>
                  {' · '}
                  Impact: <span className="font-medium">{latestAssessment.impact} — {LIKELIHOOD_LABELS[latestAssessment.impact]}</span>
                </p>
              )}
              {latestAssessment?.assessed_at && (
                <p className="text-xs text-muted-foreground">
                  Last assessed: {new Date(latestAssessment.assessed_at).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground italic">
            No score yet — add one below.
          </p>
        )}

        {/* Re-assess inline form — editors only */}
        {canEdit && (
          <div className="mt-4 pt-4 border-t">
            {!isAssessing ? (
              <button
                onClick={() => setIsAssessing(true)}
                className="text-xs text-primary hover:underline"
              >
                + Add assessment
              </button>
            ) : (
              <form onSubmit={handleAddAssessment} className="space-y-3" noValidate>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-xs font-medium">Likelihood</label>
                    <select
                      value={assessForm.likelihood}
                      onChange={(e) => setAssessForm((p) => ({ ...p, likelihood: e.target.value }))}
                      disabled={isSavingAssessment}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                    >
                      <option value="">Not set</option>
                      {[1,2,3,4,5].map((n) => (
                        <option key={n} value={n}>{n} — {LIKELIHOOD_LABELS[n]}</option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium">Impact</label>
                    <select
                      value={assessForm.impact}
                      onChange={(e) => setAssessForm((p) => ({ ...p, impact: e.target.value }))}
                      disabled={isSavingAssessment}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                    >
                      <option value="">Not set</option>
                      {[1,2,3,4,5].map((n) => (
                        <option key={n} value={n}>{n} — {LIKELIHOOD_LABELS[n]}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {assessForm.likelihood && assessForm.impact && (
                  <p className="text-xs text-muted-foreground">
                    Score preview:{' '}
                    <span className="font-semibold text-foreground">
                      {Number(assessForm.likelihood) * Number(assessForm.impact)}
                    </span>
                    {' '}({assessForm.likelihood} × {assessForm.impact})
                  </p>
                )}

                <textarea
                  value={assessForm.notes}
                  onChange={(e) => setAssessForm((p) => ({ ...p, notes: e.target.value }))}
                  placeholder="Notes (optional)"
                  rows={2}
                  disabled={isSavingAssessment}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 resize-none"
                />

                <div className="flex items-center gap-2">
                  <Button
                    type="submit"
                    size="sm"
                    disabled={!assessForm.likelihood || !assessForm.impact || isSavingAssessment}
                  >
                    {isSavingAssessment ? 'Saving…' : 'Save assessment'}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={isSavingAssessment}
                    onClick={() => {
                      setIsAssessing(false)
                      setAssessForm({ likelihood: '', impact: '', notes: '' })
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </form>
            )}
          </div>
        )}
      </div>

      {/* ---- Details ---- */}
      <div className="rounded-lg border p-5 space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Details
        </h2>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4 text-sm">
          <Detail label="Category"       value={risk.category} />
          <Detail label="Affected asset" value={risk.affected_asset} />
          {/* Owner — inline select for editors; read-only text for everyone else */}
          {canEdit && users.length > 0 ? (
            <div className={isSavingOwner ? 'opacity-50' : ''}>
              <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Owner</dt>
              <dd className="mt-1">
                {/* Invisible-border select: appearance-none removes the browser chrome,
                    the dashed underline signals editability without looking like a form field */}
                <div className="relative inline-flex items-center gap-1">
                  <select
                    value={risk.owner_id}
                    onChange={handleOwnerChange}
                    disabled={isSavingOwner}
                    className="appearance-none bg-transparent text-sm border-0 border-b border-dashed border-muted-foreground/50 hover:border-foreground focus:outline-none focus:border-primary cursor-pointer pr-4 disabled:cursor-not-allowed"
                  >
                    {users.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.full_name ?? u.email}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="h-3 w-3 text-muted-foreground pointer-events-none absolute right-0" />
                </div>
              </dd>
            </div>
          ) : (
            <Detail label="Owner" value={risk.owner?.full_name ?? risk.owner?.email ?? `User #${risk.owner_id}`} />
          )}
          <Detail label="Created"        value={new Date(risk.created_at).toLocaleDateString()} />
          <Detail label="Threat source"  value={risk.threat_source}  className="sm:col-span-2" />
          <Detail label="Threat event"   value={risk.threat_event}   className="sm:col-span-2" />
          <Detail label="Vulnerability"  value={risk.vulnerability}  className="sm:col-span-2" />
          {risk.description && (
            <Detail label="Description"  value={risk.description}    className="sm:col-span-2" />
          )}
        </dl>
      </div>

      {/* ---- Activity timeline ---- */}
      {timeline.length > 0 && (
        <div className="rounded-lg border overflow-hidden">
          <div className="px-5 py-4 border-b">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Activity
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Score changes and status updates, newest first.
            </p>
          </div>
          <ul className="divide-y divide-border">
            {(timelineExpanded ? timeline : timeline.slice(0, TIMELINE_PREVIEW)).map((entry, i) => (
              <li key={`${entry.date}-${i}`}>
                {(() => {
                  // A chevron is only needed when there are text field changes to reveal.
                  // Score and status info is always visible inline — nothing to expand there.
                  const needsExpand = entry.batch.otherFields.length > 0

                  const batchContent = (
                    <>
                      <div className="mt-0.5 shrink-0">
                        {entry.batch.assessment
                          ? <ScoreArrow score={entry.batch.assessment.risk_score} prevScore={entry.batch.prevScore} />
                          : <RefreshCw className="h-4 w-4 text-muted-foreground" />
                        }
                      </div>
                      <div className="flex-1 min-w-0 text-sm space-y-1">

                        {/* Score line — shown when this commit included a new assessment */}
                        {entry.batch.assessment && (
                          <div className="flex items-center gap-3 flex-wrap">
                            <Badge variant={scoreToBadgeVariant(entry.batch.assessment.risk_score)}>
                              {entry.batch.assessment.risk_score} — {scoreLabel(entry.batch.assessment.risk_score)}
                            </Badge>
                            <span className="text-muted-foreground text-xs">
                              {entry.batch.assessment.likelihood} (likelihood) × {entry.batch.assessment.impact} (impact)
                            </span>
                            {/* Only show status badge here when there's no separate status-change line below */}
                            {!entry.batch.statusChange && (
                              <Badge variant={entry.batch.statusAtTime as any}>
                                {STATUS_LABELS[entry.batch.statusAtTime]}
                              </Badge>
                            )}
                            {entry.batch.assessment.notes && (
                              <p className="w-full text-muted-foreground text-xs italic">
                                "{entry.batch.assessment.notes}"
                              </p>
                            )}
                          </div>
                        )}

                        {/* Status change line */}
                        {entry.batch.statusChange && (
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium text-sm">Status changed</span>
                            {entry.batch.statusChange.old_value && (
                              <>
                                <Badge variant={entry.batch.statusChange.old_value as any}>
                                  {STATUS_LABELS[entry.batch.statusChange.old_value as RiskStatus] ?? entry.batch.statusChange.old_value}
                                </Badge>
                                <span className="text-muted-foreground text-xs">to</span>
                              </>
                            )}
                            {entry.batch.statusChange.new_value && (
                              <Badge variant={entry.batch.statusChange.new_value as any}>
                                {STATUS_LABELS[entry.batch.statusChange.new_value as RiskStatus] ?? entry.batch.statusChange.new_value}
                              </Badge>
                            )}
                          </div>
                        )}

                        {/* Text field changes — names only; full before/after lives in the expanded panel */}
                        {entry.batch.otherFields.length > 0 && (
                          <p className="text-xs text-muted-foreground">
                            {(entry.batch.statusChange || entry.batch.assessment) ? 'Also updated: ' : 'Updated: '}
                            {entry.batch.otherFields.join(', ')}
                          </p>
                        )}

                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <time className="text-xs text-muted-foreground">
                          {new Date(entry.date).toLocaleDateString()}
                        </time>
                        {needsExpand
                          ? (expandedCommits.has(entry.date)
                              ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
                              : <ChevronRight className="h-4 w-4 text-muted-foreground" />)
                          : <span className="w-4" />
                        }
                      </div>
                    </>
                  )

                  return (
                    <>
                      {needsExpand ? (
                        <button
                          onClick={() => toggleCommit(entry.date)}
                          className="w-full flex items-start gap-4 px-5 py-4 hover:bg-muted/40 transition-colors text-left"
                        >
                          {batchContent}
                        </button>
                      ) : (
                        <div className="flex items-start gap-4 px-5 py-4">
                          {batchContent}
                        </div>
                      )}

                    {/* Expanded: full before/after for every changed field */}
                    {expandedCommits.has(entry.date) && (() => {
                      const commit = editHistory.find(c => c.date === entry.date)
                      if (!commit) return null
                      return (
                        <ul className="border-t bg-muted/20 divide-y divide-border">
                          {commit.changes.map((change) => (
                            <li key={change.id} className="px-8 py-3 text-xs space-y-1">
                              <p className="font-medium text-foreground">
                                {FIELD_LABELS[change.field_changed] ?? change.field_changed}
                              </p>
                              {change.field_changed === 'status' ? (
                                <div className="flex items-center gap-2">
                                  <Badge variant={change.old_value as any}>
                                    {STATUS_LABELS[change.old_value as RiskStatus] ?? change.old_value ?? 'None'}
                                  </Badge>
                                  <span className="text-muted-foreground">to</span>
                                  <Badge variant={change.new_value as any}>
                                    {STATUS_LABELS[change.new_value as RiskStatus] ?? change.new_value ?? 'None'}
                                  </Badge>
                                </div>
                              ) : (() => {
                                const isTruncated =
                                  (change.old_value?.length ?? 0) > 80 ||
                                  (change.new_value?.length ?? 0) > 80
                                return (
                                  <div className="space-y-0.5">
                                    <p className="text-muted-foreground">
                                      <span className="font-medium">Before: </span>
                                      {truncate(change.old_value) || <em>Empty</em>}
                                    </p>
                                    <p className="text-muted-foreground">
                                      <span className="font-medium">After: </span>
                                      {truncate(change.new_value) || <em>Empty</em>}
                                    </p>
                                    {isTruncated && (
                                      <button
                                        onClick={(e) => { e.stopPropagation(); setSelectedChange(change) }}
                                        className="text-xs text-primary hover:underline mt-1"
                                      >
                                        View full content →
                                      </button>
                                    )}
                                  </div>
                                )
                              })()}
                            </li>
                          ))}
                        </ul>
                      )
                    })()}
                  </>
                  )
                })()}
              </li>
            ))}
          </ul>
          {timeline.length > TIMELINE_PREVIEW && (
            <button
              onClick={() => setTimelineExpanded((e) => !e)}
              className="w-full px-5 py-3 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors border-t text-left"
            >
              {timelineExpanded ? 'Show less' : `Show ${timeline.length - TIMELINE_PREVIEW} more`}
            </button>
          )}
        </div>
      )}

      {/* ---- Treatments ---- */}
      {risk.treatments.length > 0 && (
        <div className="rounded-lg border overflow-hidden">
          <div className="px-5 py-4 border-b">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Treatment Plans
            </h2>
          </div>
          <ul className="divide-y divide-border">
            {risk.treatments.map((t) => (
              <li key={t.id} className="px-5 py-4 text-sm">
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant="outline" className="capitalize">{t.treatment_type}</Badge>
                  <Badge variant={t.status as any} className="capitalize">{t.status.replace('_', ' ')}</Badge>
                </div>
                <p>{t.mitigation_strategy}</p>
                {t.target_date && (
                  <p className="text-xs text-muted-foreground mt-1">
                    Target: {new Date(t.target_date).toLocaleDateString()}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

    </div>

    {/* ---- Full-content modal ---- */}
    {/* Opens when a truncated text field change is clicked in an expanded commit.
        The backdrop click closes it; the X button closes it.
        e.stopPropagation() on the card prevents the backdrop from firing. */}
    {selectedChange && (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        onClick={() => setSelectedChange(null)}
      >
        <div
          className="bg-background rounded-lg border shadow-lg max-w-lg w-full mx-4 p-6 space-y-4"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-sm">
              {FIELD_LABELS[selectedChange.field_changed] ?? selectedChange.field_changed}
            </h3>
            <button
              onClick={() => setSelectedChange(null)}
              className="text-muted-foreground hover:text-foreground"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-3 text-sm">
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Before</p>
              <p className="bg-muted/50 rounded p-3 whitespace-pre-wrap break-words text-foreground">
                {selectedChange.old_value || <em className="text-muted-foreground">Empty</em>}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">After</p>
              <p className="bg-muted/50 rounded p-3 whitespace-pre-wrap break-words text-foreground">
                {selectedChange.new_value || <em className="text-muted-foreground">Empty</em>}
              </p>
            </div>
          </div>
        </div>
      </div>
    )}
    </>
  )
}
