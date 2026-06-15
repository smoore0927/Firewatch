/**
 * Pure activity-timeline derivation for a risk record.
 *
 * Extracted from RiskDetailPage so the (non-trivial) commit-grouping and
 * running-state logic lives in one testable place, separate from presentation.
 *
 * Every visible event — score changes, status changes, and field edits — is
 * modelled as a single CommitBatch. When Postgres writes an assessment and
 * history rows in the same transaction they share an identical timestamp and
 * are merged into one entry. Assessment-only events (from the inline re-assess
 * form) become their own single-entry batch. This yields one unified Activity
 * list instead of two separate visual tracks.
 */
import type { Risk, RiskAssessment, RiskHistory, RiskStatus } from '@/types'
import { RISK_STATUS_LABELS } from '@/lib/constants'

// Human-readable labels for field names stored in risk_history.
export const FIELD_LABELS: Record<string, string> = {
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

export type CommitBatch = {
  date:         string
  statusChange: RiskHistory | null    // status row from this commit, if any
  otherFields:  string[]              // human-readable names of other changed fields
  assessment:   RiskAssessment | null // score change in this commit, if any
  prevScore:    number | null         // score before this commit (drives the arrow)
  statusAtTime: RiskStatus            // status after all changes in this commit
}

// Only one entry kind now — everything is a batch.
export type TimelineEntry = { kind: 'batch'; date: string; batch: CommitBatch }

// Grouped edit history (all fields, full values) for the Edit History section.
export type EditCommit = {
  date: string
  changes: RiskHistory[]
}

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

function isKnownStatus(value: string | null | undefined): value is RiskStatus {
  return value != null && Object.prototype.hasOwnProperty.call(RISK_STATUS_LABELS, value)
}

export function buildTimeline(risk: Risk): TimelineEntry[] {
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
      isKnownStatus(statusRow?.new_value) ? statusRow.new_value : currentStatus

    entries.push({
      kind: 'batch',
      date,
      batch: { date, statusChange: statusRow, otherFields, assessment, prevScore, statusAtTime },
    })

    // Advance running state for the next iteration.
    if (isKnownStatus(statusRow?.new_value)) {
      currentStatus = statusRow.new_value
    }
    if (assessment) prevScore = assessment.risk_score
  }

  return entries.reverse() // newest first for display
}

export function buildEditHistory(history: RiskHistory[]): EditCommit[] {
  const commits: EditCommit[] = []
  for (const [date, rows] of groupByCommit(history)) {
    commits.push({ date, changes: rows })
  }
  return commits.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
}
