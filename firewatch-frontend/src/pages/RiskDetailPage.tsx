/**
 * Risk detail view — full record for a single risk.
 *
 * Sections:
 *   1. Header       — risk_id, title, status badge, edit button
 *   2. Score card   — current score, severity, likelihood, impact
 *   3. Details      — category, asset, threat source/event, vulnerability, description
 *   4. Activity     — merged timeline: score changes + status changes (grouped by commit)
 *   5. Edit History — every commit with full field-level before/after, collapsible
 *   6. Responses    — mitigation plans
 */
import { useEffect, useState, useMemo, useRef, SyntheticEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { risksApi, usersApi, frameworksApi, ApiError } from '@/services/api'
import { currentScore, scoreLabel, formatLikelihoodImpact } from '@/types'
import type { Risk, RiskAssessment, RiskHistory, RiskResponse, RiskStatus, ResponseCreate, ResponseStatus, ResponseType, ResponseUpdate, User, Control, ControlFramework, RiskControlMapping, RiskControlCreate } from '@/types'
import { Badge, scoreToBadgeVariant } from '@/components/ui/badge'
import type { BadgeVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ArrowLeft, Pencil, Trash2, ArrowUp, ArrowDown, Minus, Plus, RefreshCw, ChevronDown, ChevronRight, X, MoreHorizontal } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu'

// ---- Constants --------------------------------------------------------------

const STATUS_LABELS: Record<RiskStatus, string> = {
  open:        'Open',
  in_progress: 'In Progress',
  mitigated:   'Mitigated',
  accepted:    'Accepted',
  closed:      'Closed',
}

function statusVariant(val: string | null | undefined): BadgeVariant {
  if (val && Object.prototype.hasOwnProperty.call(STATUS_LABELS, val)) return val as BadgeVariant
  return 'default'
}

function statusLabel(val: string | null | undefined): string {
  if (val && Object.prototype.hasOwnProperty.call(STATUS_LABELS, val)) return STATUS_LABELS[val as RiskStatus]
  return val ?? ''
}

// Mirrors the badge variant classes so the inline status select inherits the
// same colour as the badge it replaces.
const STATUS_COLORS: Record<RiskStatus, string> = {
  open:        'bg-blue-100   text-blue-800   dark:bg-blue-900/40   dark:text-blue-200',
  in_progress: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200',
  mitigated:   'bg-green-100  text-green-800  dark:bg-green-900/40  dark:text-green-200',
  accepted:    'bg-gray-100   text-gray-700   dark:bg-gray-800      dark:text-gray-300',
  closed:      'bg-gray-200   text-gray-500   dark:bg-gray-700      dark:text-gray-400',
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
    let group = map.get(row.changed_at)
    if (!group) {
      group = []
      map.set(row.changed_at, group)
    }
    group.push(row)
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
    const statusAtTime: RiskStatus =
      statusRow?.new_value && Object.prototype.hasOwnProperty.call(STATUS_LABELS, statusRow.new_value)
        ? (statusRow.new_value as RiskStatus)
        : currentStatus

    entries.push({
      kind: 'batch',
      date,
      batch: { date, statusChange: statusRow, otherFields, assessment, prevScore, statusAtTime },
    })

    // Advance running state for the next iteration.
    if (statusRow?.new_value && Object.prototype.hasOwnProperty.call(STATUS_LABELS, statusRow.new_value)) {
      currentStatus = statusRow.new_value as RiskStatus
    }
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

function ScoreArrow({ score, prevScore }: Readonly<{ score: number; prevScore: number | null }>) {
  if (prevScore === null) return <Minus className="h-4 w-4 text-muted-foreground" />
  if (score > prevScore)  return <ArrowUp className="h-4 w-4 text-destructive" />
  if (score < prevScore)  return <ArrowDown className="h-4 w-4 text-green-600 dark:text-green-400" />
  return <Minus className="h-4 w-4 text-muted-foreground" />
}

function Detail({ label, value, className }: Readonly<{
  label: string; value: string | null | undefined; className?: string
}>) {
  return (
    <div className={className}>
      <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</dt>
      <dd className="mt-1 text-sm">
        {value ?? <span className="italic text-muted-foreground">Not set</span>}
      </dd>
    </div>
  )
}

function ExpandChevron({ needsExpand, expanded }: Readonly<{ needsExpand: boolean; expanded: boolean }>) {
  if (!needsExpand) return <span className="w-4" />
  return expanded
    ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
    : <ChevronRight className="h-4 w-4 text-muted-foreground" />
}

function FieldChange({ change, onViewFull }: Readonly<{
  change: RiskHistory
  onViewFull: (change: RiskHistory) => void
}>) {
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
          onClick={(e) => { e.stopPropagation(); onViewFull(change) }}
          className="text-xs text-primary hover:underline mt-1"
        >
          View full content →
        </button>
      )}
    </div>
  )
}

function CommitDetail({ commit, onViewFull }: Readonly<{
  commit: EditCommit
  onViewFull: (change: RiskHistory) => void
}>) {
  return (
    <ul className="border-t bg-muted/20 divide-y divide-border">
      {commit.changes.map((change) => (
        <li key={change.id} className="px-8 py-3 text-xs space-y-1">
          <p className="font-medium text-foreground">
            {FIELD_LABELS[change.field_changed] ?? change.field_changed}
          </p>
          {change.field_changed === 'status' ? (
            <div className="flex items-center gap-2">
              <Badge variant={statusVariant(change.old_value)}>
                {statusLabel(change.old_value) || 'None'}
              </Badge>
              <span className="text-muted-foreground">to</span>
              <Badge variant={statusVariant(change.new_value)}>
                {statusLabel(change.new_value) || 'None'}
              </Badge>
            </div>
          ) : (
            <FieldChange change={change} onViewFull={onViewFull} />
          )}
        </li>
      ))}
    </ul>
  )
}

function BatchEntry({ entry, expandedCommits, editHistory, toggleCommit, onViewFull }: Readonly<{
  entry: TimelineEntry
  expandedCommits: Set<string>
  editHistory: EditCommit[]
  toggleCommit: (date: string) => void
  onViewFull: (change: RiskHistory) => void
}>) {
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

        {entry.batch.assessment && (
          <div className="flex items-center gap-3 flex-wrap">
            <Badge variant={scoreToBadgeVariant(entry.batch.assessment.risk_score)}>
              {entry.batch.assessment.risk_score} — {scoreLabel(entry.batch.assessment.risk_score)}
            </Badge>
            <span className="text-muted-foreground text-xs">
              {formatLikelihoodImpact(entry.batch.assessment.likelihood, entry.batch.assessment.impact)} (likelihood × impact)
            </span>
            {entry.batch.assessment.residual_risk_score != null && (
              <span className="text-muted-foreground text-xs">
                Residual: <span className="font-medium text-foreground">{entry.batch.assessment.residual_risk_score}</span>
                {' '}({formatLikelihoodImpact(entry.batch.assessment.residual_likelihood!, entry.batch.assessment.residual_impact!)})
              </span>
            )}
            {!entry.batch.statusChange && (
              <Badge variant={entry.batch.statusAtTime}>
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

        {entry.batch.statusChange && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm">Status changed</span>
            {entry.batch.statusChange.old_value && (
              <>
                <Badge variant={statusVariant(entry.batch.statusChange.old_value)}>
                  {statusLabel(entry.batch.statusChange.old_value) || entry.batch.statusChange.old_value}
                </Badge>
                <span className="text-muted-foreground text-xs">to</span>
              </>
            )}
            {entry.batch.statusChange.new_value && (
              <Badge variant={statusVariant(entry.batch.statusChange.new_value)}>
                {statusLabel(entry.batch.statusChange.new_value) || entry.batch.statusChange.new_value}
              </Badge>
            )}
          </div>
        )}

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
        <ExpandChevron needsExpand={needsExpand} expanded={expandedCommits.has(entry.date)} />
      </div>
    </>
  )

  const commit = editHistory.find(c => c.date === entry.date)

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
      {expandedCommits.has(entry.date) && commit && (
        <CommitDetail commit={commit} onViewFull={onViewFull} />
      )}
    </>
  )
}

function canEditRisk(user: User | null, risk: Risk | null): boolean {
  return (
    user?.role === 'admin' ||
    user?.role === 'security_analyst' ||
    (user?.role === 'risk_owner' && risk !== null && risk.owner_id === user.id)
  )
}

function FullContentModal({ change, onClose }: Readonly<{
  change: RiskHistory | null
  onClose: () => void
}>) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    if (change) ref.current?.showModal()
  }, [change])

  if (!change) return null

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className="bg-background rounded-lg border shadow-lg m-auto max-w-[min(32rem,calc(100vw-2rem))] w-full p-6 space-y-4 backdrop:bg-black/50"
    >
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm">
          {FIELD_LABELS[change.field_changed] ?? change.field_changed}
        </h3>
        <button
          type="button"
          onClick={() => ref.current?.close()}
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
            {change.old_value || <em className="text-muted-foreground">Empty</em>}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">After</p>
          <p className="bg-muted/50 rounded p-3 whitespace-pre-wrap break-words text-foreground">
            {change.new_value || <em className="text-muted-foreground">Empty</em>}
          </p>
        </div>
      </div>
    </dialog>
  )
}

function DeleteConfirmDialog({
  open,
  isDeleting,
  errorMessage,
  riskId,
  riskTitle,
  onConfirm,
  onClose,
}: Readonly<{
  open: boolean
  isDeleting: boolean
  errorMessage: string | null
  riskId: string
  riskTitle: string
  onConfirm: () => void
  onClose: () => void
}>) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    if (open) ref.current?.showModal()
  }, [open])

  function handleCancelEvent(e: SyntheticEvent<HTMLDialogElement>) {
    if (isDeleting) e.preventDefault()
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="delete-dialog-title"
      onCancel={handleCancelEvent}
      onClose={onClose}
      className="bg-background rounded-lg border shadow-lg m-auto max-w-[min(28rem,calc(100vw-2rem))] w-full p-6 space-y-4 backdrop:bg-black/50"
    >
      <h3 id="delete-dialog-title" className="font-semibold text-base">Delete this risk?</h3>
      <div className="text-sm text-muted-foreground space-y-3">
        <p>
          Are you sure you want to delete{' '}
          <span className="font-semibold text-foreground">
            {riskId} — {riskTitle}
          </span>?
        </p>
        <p>
          This is a soft delete: the risk will be removed from the register
          but its full history and audit trail are retained.
        </p>
      </div>
      {errorMessage && (
        <p className="text-sm text-destructive">{errorMessage}</p>
      )}
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={isDeleting}
          onClick={() => ref.current?.close()}
        >
          Cancel
        </Button>
        <Button
          variant="destructive"
          size="sm"
          disabled={isDeleting}
          onClick={onConfirm}
        >
          {isDeleting ? 'Deleting…' : 'Delete'}
        </Button>
      </div>
    </dialog>
  )
}

// ---- Response Plans ---------------------------------------------------------

const RESPONSE_TYPE_LABELS: Record<ResponseType, string> = {
  mitigate: 'Mitigate',
  accept:   'Accept',
  transfer: 'Transfer',
  avoid:    'Avoid',
}

const RESPONSE_STATUS_LABELS: Record<ResponseStatus, string> = {
  planned:     'Planned',
  in_progress: 'In Progress',
  completed:   'Completed',
  deferred:    'Deferred',
}

const RESPONSE_STATUS_COLORS: Record<ResponseStatus, string> = {
  planned:     'bg-blue-100   text-blue-800   dark:bg-blue-900/40   dark:text-blue-200',
  in_progress: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200',
  completed:   'bg-green-100  text-green-800  dark:bg-green-900/40  dark:text-green-200',
  deferred:    'bg-gray-100   text-gray-700   dark:bg-gray-800      dark:text-gray-300',
}

function responseStatusVariant(val: ResponseStatus): BadgeVariant {
  // Reuse risk-status badge variants where the colour intent matches.
  const map: Record<ResponseStatus, BadgeVariant> = {
    planned:     'open',
    in_progress: 'in_progress',
    completed:   'mitigated',
    deferred:    'accepted',
  }
  return map[val]
}

function isOverdue(targetDate: string | null, status: ResponseStatus): boolean {
  if (!targetDate || status === 'completed') return false
  const t = new Date(targetDate)
  t.setHours(0, 0, 0, 0)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return t.getTime() < today.getTime()
}

function dateInputValue(iso: string | null): string {
  return iso ? iso.slice(0, 10) : ''
}

function toIsoOrNull(dateString: string): string | null {
  if (!dateString) return null
  return new Date(dateString).toISOString()
}

type ResponseFormState = {
  response_type:        ResponseType
  mitigation_strategy:  string
  target_date:          string
  notes:                string
}

const EMPTY_FORM: ResponseFormState = {
  response_type:       'mitigate',
  mitigation_strategy: '',
  target_date:         '',
  notes:               '',
}

function ResponseForm({
  initial,
  isSubmitting,
  errorMessage,
  submitLabel,
  onSubmit,
  onCancel,
  idPrefix,
}: Readonly<{
  initial: ResponseFormState
  isSubmitting: boolean
  errorMessage: string | null
  submitLabel: string
  onSubmit: (next: ResponseFormState) => void
  onCancel: () => void
  idPrefix: string
}>) {
  const [form, setForm] = useState<ResponseFormState>(initial)

  function handleSubmit(e: SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    onSubmit(form)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-md border bg-muted/20 p-4" noValidate>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor={`${idPrefix}-type`}>Response type <span aria-hidden="true" className="text-destructive">*</span></Label>
          <select
            id={`${idPrefix}-type`}
            value={form.response_type}
            onChange={(e) => setForm((p) => ({ ...p, response_type: e.target.value as ResponseType }))}
            disabled={isSubmitting}
            required
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          >
            {(Object.keys(RESPONSE_TYPE_LABELS) as ResponseType[]).map((t) => (
              <option key={t} value={t}>{RESPONSE_TYPE_LABELS[t]}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor={`${idPrefix}-target-date`}>Target date</Label>
          <Input
            id={`${idPrefix}-target-date`}
            type="date"
            value={form.target_date}
            onChange={(e) => setForm((p) => ({ ...p, target_date: e.target.value }))}
            disabled={isSubmitting}
          />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor={`${idPrefix}-strategy`}>Mitigation strategy <span aria-hidden="true" className="text-destructive">*</span></Label>
        <Textarea
          id={`${idPrefix}-strategy`}
          value={form.mitigation_strategy}
          onChange={(e) => setForm((p) => ({ ...p, mitigation_strategy: e.target.value }))}
          disabled={isSubmitting}
          required
          rows={3}
        />
      </div>

      <div className="space-y-1">
        <Label htmlFor={`${idPrefix}-notes`}>Notes</Label>
        <Textarea
          id={`${idPrefix}-notes`}
          value={form.notes}
          onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
          disabled={isSubmitting}
          rows={2}
        />
      </div>

      {errorMessage && (
        <p className="text-sm text-destructive">{errorMessage}</p>
      )}

      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={isSubmitting}>
          {isSubmitting ? 'Saving…' : submitLabel}
        </Button>
        <Button type="button" size="sm" variant="ghost" disabled={isSubmitting} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function ResponseRow({
  response,
  canEdit,
  riskId,
  isEditing,
  isDeleteConfirming,
  onStartEdit,
  onCancelEdit,
  onEditSaved,
  onAskDelete,
  onCancelDelete,
  onConfirmDelete,
  onStatusQuickChange,
}: Readonly<{
  response: RiskResponse
  canEdit: boolean
  riskId: string
  isEditing: boolean
  isDeleteConfirming: boolean
  onStartEdit: () => void
  onCancelEdit: () => void
  onEditSaved: () => void
  onAskDelete: () => void
  onCancelDelete: () => void
  onConfirmDelete: () => Promise<void>
  onStatusQuickChange: (newStatus: ResponseStatus) => Promise<void>
}>) {
  const [editError, setEditError] = useState<string | null>(null)
  const [isSavingEdit, setIsSavingEdit] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isSavingStatus, setIsSavingStatus] = useState(false)

  const overdue = isOverdue(response.target_date, response.status)
  const hasDates = response.target_date || response.completion_date

  async function handleEditSubmit(form: ResponseFormState) {
    setEditError(null)
    setIsSavingEdit(true)
    try {
      const payload: ResponseUpdate = {}
      if (form.response_type !== response.response_type) {
        payload.response_type = form.response_type
      }
      if (form.mitigation_strategy !== response.mitigation_strategy) {
        payload.mitigation_strategy = form.mitigation_strategy
      }
      const originalTarget = dateInputValue(response.target_date)
      if (form.target_date !== originalTarget) {
        payload.target_date = form.target_date ? toIsoOrNull(form.target_date) : null
      }
      const originalNotes = response.notes ?? ''
      if (form.notes !== originalNotes) {
        payload.notes = form.notes || null
      }
      if (Object.keys(payload).length === 0) {
        onCancelEdit()
        return
      }
      await risksApi.updateResponse(riskId, response.id, payload)
      onEditSaved()
    } catch (err) {
      setEditError(err instanceof ApiError ? err.message : 'Could not update this response.')
    } finally {
      setIsSavingEdit(false)
    }
  }

  async function handleDeleteConfirm() {
    setIsDeleting(true)
    try {
      await onConfirmDelete()
    } finally {
      setIsDeleting(false)
    }
  }

  async function handleStatusChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value as ResponseStatus
    if (next === response.status) return
    setIsSavingStatus(true)
    try {
      await onStatusQuickChange(next)
    } finally {
      setIsSavingStatus(false)
    }
  }

  return (
    <li className="px-5 py-4 text-sm space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="outline" className="capitalize">
            {RESPONSE_TYPE_LABELS[response.response_type]}
          </Badge>
          {canEdit ? (
            <div className={`relative inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium gap-1 ${RESPONSE_STATUS_COLORS[response.status]} ${isSavingStatus ? 'opacity-50' : ''}`}>
              <span>{RESPONSE_STATUS_LABELS[response.status]}</span>
              <ChevronDown className="h-3 w-3 shrink-0 opacity-60" />
              <select
                value={response.status}
                onChange={handleStatusChange}
                disabled={isSavingStatus}
                aria-label={`Change response status for response ${response.id}`}
                className="absolute inset-0 w-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
              >
                {(Object.keys(RESPONSE_STATUS_LABELS) as ResponseStatus[]).map((s) => (
                  <option key={s} value={s}>{RESPONSE_STATUS_LABELS[s]}</option>
                ))}
              </select>
            </div>
          ) : (
            <Badge variant={responseStatusVariant(response.status)}>
              {RESPONSE_STATUS_LABELS[response.status]}
            </Badge>
          )}
          {overdue && (
            <Badge variant="destructive">Overdue</Badge>
          )}
        </div>
        {canEdit && !isEditing && !isDeleteConfirming && (
          <div className="flex items-center gap-1 shrink-0">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              aria-label={`Edit response ${response.id}`}
              onClick={onStartEdit}
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 text-destructive hover:text-destructive"
              aria-label={`Delete response ${response.id}`}
              onClick={onAskDelete}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}
      </div>

      {!isEditing && (
        <>
          <p>{response.mitigation_strategy}</p>
          {hasDates && (
            <p className="text-xs text-muted-foreground">
              {response.target_date && (
                <span>Target: {new Date(response.target_date).toLocaleDateString()}</span>
              )}
              {response.target_date && response.completion_date && <span>{' · '}</span>}
              {response.completion_date && (
                <span>Completed: {new Date(response.completion_date).toLocaleDateString()}</span>
              )}
            </p>
          )}
          {response.notes && (
            <p className="text-xs text-muted-foreground italic">"{response.notes}"</p>
          )}
        </>
      )}

      {isEditing && (
        <ResponseForm
          initial={{
            response_type:       response.response_type,
            mitigation_strategy: response.mitigation_strategy,
            target_date:         dateInputValue(response.target_date),
            notes:               response.notes ?? '',
          }}
          isSubmitting={isSavingEdit}
          errorMessage={editError}
          submitLabel="Save"
          onSubmit={handleEditSubmit}
          onCancel={() => { setEditError(null); onCancelEdit() }}
          idPrefix={`response-edit-${response.id}`}
        />
      )}

      {isDeleteConfirming && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs">
          <span className="text-destructive">Delete this response?</span>
          <Button
            type="button"
            size="sm"
            variant="destructive"
            disabled={isDeleting}
            onClick={handleDeleteConfirm}
          >
            {isDeleting ? 'Deleting…' : 'Yes, delete'}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={isDeleting}
            onClick={onCancelDelete}
          >
            Cancel
          </Button>
        </div>
      )}
    </li>
  )
}

function ResponsePlans({
  risk,
  canEdit,
  onChanged,
}: Readonly<{
  risk: Risk
  canEdit: boolean
  onChanged: () => void
}>) {
  const [isCreating, setIsCreating] = useState(false)
  const [isSavingCreate, setIsSavingCreate] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [editingResponseId, setEditingResponseId] = useState<number | null>(null)
  const [deletingResponseId, setDeletingResponseId] = useState<number | null>(null)

  async function handleCreate(form: ResponseFormState) {
    setCreateError(null)
    setIsSavingCreate(true)
    try {
      const payload: ResponseCreate = {
        response_type:       form.response_type,
        mitigation_strategy: form.mitigation_strategy,
        ...(form.target_date && { target_date: toIsoOrNull(form.target_date) }),
        ...(form.notes && { notes: form.notes }),
      }
      await risksApi.addResponse(risk.risk_id, payload)
      setIsCreating(false)
      onChanged()
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : 'Could not add this response.')
    } finally {
      setIsSavingCreate(false)
    }
  }

  async function handleDelete(responseId: number) {
    try {
      await risksApi.deleteResponse(risk.risk_id, responseId)
      setDeletingResponseId(null)
      onChanged()
    } catch {
      // Leave the confirm UI open on failure; user can retry or cancel.
    }
  }

  async function handleStatusChange(responseId: number, status: ResponseStatus) {
    await risksApi.updateResponse(risk.risk_id, responseId, { status })
    onChanged()
  }

  return (
    <div className="rounded-lg border overflow-hidden">
      <div className="px-5 py-4 border-b flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Response Plans
        </h2>
        {canEdit && !isCreating && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="gap-1"
            onClick={() => { setCreateError(null); setIsCreating(true) }}
          >
            <Plus className="h-3 w-3" /> Add response
          </Button>
        )}
      </div>

      {isCreating && (
        <div className="px-5 py-4 border-b">
          <ResponseForm
            initial={EMPTY_FORM}
            isSubmitting={isSavingCreate}
            errorMessage={createError}
            submitLabel="Save"
            onSubmit={handleCreate}
            onCancel={() => { setCreateError(null); setIsCreating(false) }}
            idPrefix="response-create"
          />
        </div>
      )}

      {risk.responses.length === 0 ? (
        <p className="px-5 py-4 text-sm text-muted-foreground">No response plans yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {risk.responses.map((r) => (
            <ResponseRow
              key={r.id}
              response={r}
              canEdit={canEdit}
              riskId={risk.risk_id}
              isEditing={editingResponseId === r.id}
              isDeleteConfirming={deletingResponseId === r.id}
              onStartEdit={() => { setDeletingResponseId(null); setEditingResponseId(r.id) }}
              onCancelEdit={() => setEditingResponseId(null)}
              onEditSaved={() => { setEditingResponseId(null); onChanged() }}
              onAskDelete={() => { setEditingResponseId(null); setDeletingResponseId(r.id) }}
              onCancelDelete={() => setDeletingResponseId(null)}
              onConfirmDelete={() => handleDelete(r.id)}
              onStatusQuickChange={(status) => handleStatusChange(r.id, status)}
            />
          ))}
        </ul>
      )}
    </div>
  )
}

// ---- Mapped Controls --------------------------------------------------------

const MAPPING_TYPE_LABELS: Record<string, string> = {
  mitigates: 'Mitigates',
  monitors:  'Monitors',
  detects:   'Detects',
}

const MAPPING_TYPES = ['mitigates', 'monitors', 'detects'] as const

function AddControlForm({
  riskId,
  onCancel,
  onAdded,
}: Readonly<{
  riskId: string
  onCancel: () => void
  onAdded: () => void
}>) {
  const [frameworks, setFrameworks] = useState<ControlFramework[]>([])
  const [frameworkId, setFrameworkId] = useState<number | ''>('')
  const [search, setSearch] = useState('')
  const [controls, setControls] = useState<Control[]>([])
  const [controlId, setControlId] = useState<number | ''>('')
  const [mappingType, setMappingType] = useState<string>('mitigates')
  const [notes, setNotes] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    frameworksApi.getFrameworks().then(setFrameworks).catch(() => { /* read-only fallback */ })
  }, [])

  // Debounced control search whenever the framework or query changes.
  useEffect(() => {
    if (frameworkId === '') {
      setControls([])
      return
    }
    const handle = setTimeout(() => {
      frameworksApi.getFrameworkControls(frameworkId, search.trim() || undefined)
        .then(setControls)
        .catch(() => setControls([]))
    }, 250)
    return () => clearTimeout(handle)
  }, [frameworkId, search])

  async function handleSubmit(e: SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (controlId === '') return
    setErrorMessage(null)
    setIsSubmitting(true)
    try {
      const payload: RiskControlCreate = {
        control_id:   controlId,
        mapping_type: mappingType,
        ...(notes.trim() && { notes: notes.trim() }),
      }
      await frameworksApi.addRiskControl(riskId, payload)
      onAdded()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setErrorMessage('This control is already mapped to this risk.')
      } else {
        setErrorMessage(err instanceof ApiError ? err.message : 'Could not add this control.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const selectClass = 'w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50'

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-md border bg-muted/20 p-4" noValidate>
      <div className="space-y-1">
        <Label htmlFor="control-framework">Framework <span aria-hidden="true" className="text-destructive">*</span></Label>
        <select
          id="control-framework"
          value={frameworkId}
          onChange={(e) => {
            setFrameworkId(e.target.value ? Number(e.target.value) : '')
            setControlId('')
          }}
          disabled={isSubmitting}
          required
          className={selectClass}
        >
          <option value="">Select a framework…</option>
          {frameworks.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}{f.version ? ` (${f.version})` : ''}
            </option>
          ))}
        </select>
      </div>

      {frameworkId !== '' && (
        <>
          <div className="space-y-1">
            <Label htmlFor="control-search">Search controls</Label>
            <Input
              id="control-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter by control ID or title…"
              disabled={isSubmitting}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="control-picker">Control <span aria-hidden="true" className="text-destructive">*</span></Label>
            <select
              id="control-picker"
              value={controlId}
              onChange={(e) => setControlId(e.target.value ? Number(e.target.value) : '')}
              disabled={isSubmitting}
              required
              size={6}
              className={selectClass}
            >
              {controls.length === 0 ? (
                <option value="" disabled>No controls found</option>
              ) : (
                controls.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.control_id} — {c.title}
                  </option>
                ))
              )}
            </select>
          </div>
        </>
      )}

      <div className="space-y-1">
        <Label htmlFor="control-mapping-type">Mapping type <span aria-hidden="true" className="text-destructive">*</span></Label>
        <select
          id="control-mapping-type"
          value={mappingType}
          onChange={(e) => setMappingType(e.target.value)}
          disabled={isSubmitting}
          required
          className={selectClass}
        >
          {MAPPING_TYPES.map((t) => (
            <option key={t} value={t}>{MAPPING_TYPE_LABELS[t]}</option>
          ))}
        </select>
      </div>

      <div className="space-y-1">
        <Label htmlFor="control-notes">Notes</Label>
        <Textarea
          id="control-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          disabled={isSubmitting}
          rows={2}
        />
      </div>

      {errorMessage && (
        <p className="text-sm text-destructive">{errorMessage}</p>
      )}

      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={isSubmitting || controlId === ''}>
          {isSubmitting ? 'Saving…' : 'Add control'}
        </Button>
        <Button type="button" size="sm" variant="ghost" disabled={isSubmitting} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function MappedControlRow({
  mapping,
  canEdit,
  onRemove,
}: Readonly<{
  mapping: RiskControlMapping
  canEdit: boolean
  onRemove: () => Promise<void>
}>) {
  const [isRemoving, setIsRemoving] = useState(false)

  async function handleRemove() {
    setIsRemoving(true)
    try {
      await onRemove()
    } finally {
      setIsRemoving(false)
    }
  }

  return (
    <li className="px-5 py-4 text-sm space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-1 min-w-0">
          <p className="font-medium">
            <span className="font-mono">{mapping.control.control_id}</span> — {mapping.control.title}
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline">{mapping.control.framework_name}</Badge>
            <Badge variant="outline" className="capitalize">
              {MAPPING_TYPE_LABELS[mapping.mapping_type] ?? mapping.mapping_type}
            </Badge>
          </div>
          {mapping.notes && (
            <p className="text-xs text-muted-foreground italic">"{mapping.notes}"</p>
          )}
        </div>
        {canEdit && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-destructive hover:text-destructive shrink-0"
            disabled={isRemoving}
            aria-label={`Remove control ${mapping.control.control_id}`}
            onClick={handleRemove}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </li>
  )
}

function MappedControls({
  riskId,
  canEdit,
}: Readonly<{
  riskId: string
  canEdit: boolean
}>) {
  const [mappings, setMappings] = useState<RiskControlMapping[]>([])
  const [isCreating, setIsCreating] = useState(false)

  function load() {
    frameworksApi.getRiskControls(riskId).then(setMappings).catch(() => { /* read-only fallback */ })
  }

  useEffect(() => {
    frameworksApi.getRiskControls(riskId).then(setMappings).catch(() => { /* read-only fallback */ })
  }, [riskId])

  async function handleRemove(mappingId: number) {
    await frameworksApi.deleteRiskControl(riskId, mappingId)
    load()
  }

  return (
    <div className="rounded-lg border overflow-hidden">
      <div className="px-5 py-4 border-b flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Mapped Controls
        </h2>
        {canEdit && !isCreating && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="gap-1"
            onClick={() => setIsCreating(true)}
          >
            <Plus className="h-3 w-3" /> Add control
          </Button>
        )}
      </div>

      {isCreating && (
        <div className="px-5 py-4 border-b">
          <AddControlForm
            riskId={riskId}
            onCancel={() => setIsCreating(false)}
            onAdded={() => { setIsCreating(false); load() }}
          />
        </div>
      )}

      {mappings.length === 0 ? (
        <p className="px-5 py-4 text-sm text-muted-foreground">No controls mapped yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {mappings.map((m) => (
            <MappedControlRow
              key={m.id}
              mapping={m}
              canEdit={canEdit}
              onRemove={() => handleRemove(m.id)}
            />
          ))}
        </ul>
      )}
    </div>
  )
}

// ---- Header -----------------------------------------------------------------

function RiskHeader({
  risk,
  canEdit,
  userRole,
  isSavingStatus,
  onStatusChange,
  onEdit,
  onBack,
  onRequestDelete,
}: Readonly<{
  risk: Risk
  canEdit: boolean
  userRole: string | undefined
  isSavingStatus: boolean
  onStatusChange: (e: React.ChangeEvent<HTMLSelectElement>) => void
  onEdit: () => void
  onBack: () => void
  onRequestDelete: () => void
}>) {
  return (
    <div>
      <button
        onClick={onBack}
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
                onChange={onStatusChange}
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
            <Badge variant={risk.status}>{STATUS_LABELS[risk.status]}</Badge>
          )}
          {canEdit && (
            <Button size="sm" variant="outline" className="gap-2"
              onClick={onEdit}>
              <Pencil className="h-3 w-3" /> Edit
            </Button>
          )}
          {userRole === 'admin' && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="outline" aria-label="More actions">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={onRequestDelete}
                  className="text-destructive focus:text-destructive"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete this risk
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    </div>
  )
}

// ---- Score card -------------------------------------------------------------

function ScoreCard({
  score,
  latestAssessment,
  canEdit,
  isAssessing,
  isSavingAssessment,
  assessForm,
  setAssessForm,
  onStartAssessing,
  onCancelAssessing,
  onSubmit,
}: Readonly<{
  score: number | null
  latestAssessment: RiskAssessment | null
  canEdit: boolean
  isAssessing: boolean
  isSavingAssessment: boolean
  assessForm: { residual_likelihood: string; residual_impact: string; notes: string }
  setAssessForm: React.Dispatch<React.SetStateAction<{ residual_likelihood: string; residual_impact: string; notes: string }>>
  onStartAssessing: () => void
  onCancelAssessing: () => void
  onSubmit: (e: SyntheticEvent<HTMLFormElement>) => void
}>) {
  return (
    <div className="rounded-lg border p-5">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-4">
        Current Score
      </h2>
      {score === null ? (
        <p className="text-sm text-muted-foreground italic">
          No score yet — set an initial score on the edit page.
        </p>
      ) : (
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
                Inherent (likelihood × impact): <span className="font-medium">{formatLikelihoodImpact(latestAssessment.likelihood, latestAssessment.impact)} = {latestAssessment.risk_score}</span>
              </p>
            )}
            {latestAssessment?.residual_risk_score != null && (
              <p className="text-xs text-muted-foreground">
                Residual: <strong className="font-medium text-foreground">{latestAssessment.residual_risk_score}</strong>
                {' '}({formatLikelihoodImpact(latestAssessment.residual_likelihood!, latestAssessment.residual_impact!)})
              </p>
            )}
            {latestAssessment?.assessed_at && (
              <p className="text-xs text-muted-foreground">
                Last reviewed: {new Date(latestAssessment.assessed_at).toLocaleDateString()}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Re-assess inline form — editors only */}
      {canEdit && (
        <div className="mt-4 pt-4 border-t">
          {isAssessing ? (
            <form onSubmit={onSubmit} className="space-y-3" noValidate>
              <div className="space-y-2">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label htmlFor="assess-residual-likelihood" className="text-xs font-medium">Residual Likelihood</label>
                    <select
                      id="assess-residual-likelihood"
                      value={assessForm.residual_likelihood}
                      onChange={(e) => setAssessForm((p) => ({ ...p, residual_likelihood: e.target.value }))}
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
                    <label htmlFor="assess-residual-impact" className="text-xs font-medium">Residual Impact</label>
                    <select
                      id="assess-residual-impact"
                      value={assessForm.residual_impact}
                      onChange={(e) => setAssessForm((p) => ({ ...p, residual_impact: e.target.value }))}
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
                {assessForm.residual_likelihood && assessForm.residual_impact && (
                  <p className="text-xs text-muted-foreground">
                    Residual score preview:{' '}
                    <span className="font-semibold text-foreground">
                      {Number(assessForm.residual_likelihood) * Number(assessForm.residual_impact)}
                    </span>
                    {' '}({formatLikelihoodImpact(Number(assessForm.residual_likelihood), Number(assessForm.residual_impact))})
                  </p>
                )}
              </div>

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
                  disabled={isSavingAssessment}
                >
                  {isSavingAssessment ? 'Saving…' : 'Save review'}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={isSavingAssessment}
                  onClick={onCancelAssessing}
                >
                  Cancel
                </Button>
              </div>
            </form>
          ) : (
            latestAssessment !== null && (
              <button
                onClick={onStartAssessing}
                className="text-xs text-primary hover:underline"
              >
                + Log review
              </button>
            )
          )}
        </div>
      )}
    </div>
  )
}

// ---- Activity timeline ------------------------------------------------------

function ActivityTimeline({
  timeline,
  editHistory,
  previewCount,
  expanded,
  onToggleExpanded,
  expandedCommits,
  toggleCommit,
  onViewFull,
}: Readonly<{
  timeline: ReturnType<typeof buildTimeline>
  editHistory: ReturnType<typeof buildEditHistory>
  previewCount: number
  expanded: boolean
  onToggleExpanded: () => void
  expandedCommits: Set<string>
  toggleCommit: (date: string) => void
  onViewFull: (change: RiskHistory) => void
}>) {
  if (timeline.length === 0) return null
  return (
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
        {(expanded ? timeline : timeline.slice(0, previewCount)).map((entry) => (
          <li key={entry.date}>
            <BatchEntry
              entry={entry}
              expandedCommits={expandedCommits}
              editHistory={editHistory}
              toggleCommit={toggleCommit}
              onViewFull={onViewFull}
            />
          </li>
        ))}
      </ul>
      {timeline.length > previewCount && (
        <button
          onClick={onToggleExpanded}
          className="w-full px-5 py-3 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors border-t text-left"
        >
          {expanded ? 'Show less' : `Show ${timeline.length - previewCount} more`}
        </button>
      )}
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

  const canEdit = canEditRisk(user, risk)

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
      .catch(() => { /* 403 for non-editors — read-only fallback */ })
  }, [])

  // ---- Inline status change ----
  const [isSavingStatus, setIsSavingStatus] = useState(false)

  async function handleStatusChange(e: React.ChangeEvent<HTMLSelectElement>) {
    if (!riskId) return
    const newStatus = e.target.value
    if (!Object.prototype.hasOwnProperty.call(STATUS_LABELS, newStatus)) return
    setIsSavingStatus(true)
    try {
      await risksApi.update(riskId, { status: newStatus as RiskStatus })
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
  const [assessForm, setAssessForm] = useState({
    residual_likelihood: '',
    residual_impact: '',
    notes: '',
  })

  async function handleAddAssessment(e: SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!riskId || !latestAssessment) return
    setIsSavingAssessment(true)
    try {
      const hasResidual = !!assessForm.residual_likelihood && !!assessForm.residual_impact
      await risksApi.addAssessment(riskId, {
        likelihood: latestAssessment.likelihood,
        impact:     latestAssessment.impact,
        ...(assessForm.notes.trim() && { notes: assessForm.notes.trim() }),
        ...(hasResidual && {
          residual_likelihood: Number(assessForm.residual_likelihood),
          residual_impact:     Number(assessForm.residual_impact),
        }),
      })
      setIsAssessing(false)
      setAssessForm({
        residual_likelihood: '',
        residual_impact: '',
        notes: '',
      })
      loadRisk()
    } finally {
      setIsSavingAssessment(false)
    }
  }

  // ---- Delete ----
  const [isDeleteOpen, setIsDeleteOpen] = useState(false)
  const [isDeleting, setIsDeleting]     = useState(false)
  const [deleteError, setDeleteError]   = useState<string | null>(null)

  async function handleDelete() {
    if (!riskId) return
    setIsDeleting(true)
    setDeleteError(null)
    try {
      await risksApi.delete(riskId)
      setIsDeleteOpen(false)
      navigate('/risks')
    } catch (err) {
      if (err instanceof ApiError) {
        setDeleteError(err.message)
      } else {
        setDeleteError('Could not delete this risk. Please try again.')
      }
    } finally {
      setIsDeleting(false)
    }
  }

  function toggleCommit(date: string) {
    setExpandedCommits((prev) => {
      const next = new Set(prev)
      if (next.has(date)) {
        next.delete(date)
      } else {
        next.add(date)
      }
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
      <RiskHeader
        risk={risk}
        canEdit={canEdit}
        userRole={user?.role}
        isSavingStatus={isSavingStatus}
        onStatusChange={handleStatusChange}
        onEdit={() => navigate(`/risks/${risk.risk_id}/edit`)}
        onBack={() => navigate('/risks')}
        onRequestDelete={() => { setDeleteError(null); setIsDeleteOpen(true) }}
      />

      {/* ---- Score card ---- */}
      <ScoreCard
        score={score}
        latestAssessment={latestAssessment}
        canEdit={canEdit}
        isAssessing={isAssessing}
        isSavingAssessment={isSavingAssessment}
        assessForm={assessForm}
        setAssessForm={setAssessForm}
        onStartAssessing={() => setIsAssessing(true)}
        onCancelAssessing={() => {
          setIsAssessing(false)
          setAssessForm({
            residual_likelihood: '',
            residual_impact: '',
            notes: '',
          })
        }}
        onSubmit={handleAddAssessment}
      />

      {/* ---- Details ---- */}
      <div className="rounded-lg border p-5 space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Details
        </h2>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4 text-sm">
          <Detail label="Category"       value={risk.category} />
          <Detail label="Created"        value={new Date(risk.created_at).toLocaleDateString()} />
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
          <Detail label="Next review"    value={risk.next_review_date ? new Date(risk.next_review_date).toLocaleDateString() : null} />
          <Detail label="Affected asset" value={risk.affected_asset} />
          <Detail label="Threat source"  value={risk.threat_source}  className="sm:col-span-2" />
          <Detail label="Threat event"   value={risk.threat_event}   className="sm:col-span-2" />
          <Detail label="Vulnerability"  value={risk.vulnerability}  className="sm:col-span-2" />
          {risk.description && (
            <Detail label="Description"  value={risk.description}    className="sm:col-span-2" />
          )}
        </dl>
      </div>

      {/* ---- Responses ---- */}
      <ResponsePlans risk={risk} canEdit={canEdit} onChanged={loadRisk} />

      {/* ---- Mapped controls ---- */}
      <MappedControls riskId={risk.risk_id} canEdit={canEdit} />

      {/* ---- Activity timeline ---- */}
      <ActivityTimeline
        timeline={timeline}
        editHistory={editHistory}
        previewCount={TIMELINE_PREVIEW}
        expanded={timelineExpanded}
        onToggleExpanded={() => setTimelineExpanded((e) => !e)}
        expandedCommits={expandedCommits}
        toggleCommit={toggleCommit}
        onViewFull={setSelectedChange}
      />

    </div>

    <FullContentModal
      change={selectedChange}
      onClose={() => setSelectedChange(null)}
    />

    <DeleteConfirmDialog
      open={isDeleteOpen}
      isDeleting={isDeleting}
      errorMessage={deleteError}
      riskId={risk.risk_id}
      riskTitle={risk.title}
      onConfirm={handleDelete}
      onClose={() => {
        setIsDeleteOpen(false)
        setDeleteError(null)
      }}
    />
    </>
  )
}
