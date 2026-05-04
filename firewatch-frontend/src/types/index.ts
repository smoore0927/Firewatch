/**
 * TypeScript interfaces that mirror the backend Pydantic schemas.
 *
 * Keeping these in sync with the backend is a manual process for now.
 * A future improvement would be to generate these automatically from the
 * OpenAPI schema the FastAPI backend exposes at /openapi.json.
 */

// -------------------------------------------------------------------------
// Auth
// -------------------------------------------------------------------------

export interface LoginRequest {
  email: string
  password: string
}

export interface LoginResponse {
  user_id: number
  email: string
  role: UserRole
  full_name: string | null
}

// -------------------------------------------------------------------------
// Users
// -------------------------------------------------------------------------

export type UserRole =
  | 'admin'
  | 'security_analyst'
  | 'risk_owner'
  | 'executive_viewer'

export interface User {
  id: number
  email: string
  full_name: string | null
  role: UserRole
  is_active: boolean
  created_at: string
}

// -------------------------------------------------------------------------
// Risks
// -------------------------------------------------------------------------

export type RiskStatus =
  | 'open'
  | 'in_progress'
  | 'mitigated'
  | 'accepted'
  | 'closed'

export type TreatmentType = 'mitigate' | 'accept' | 'transfer' | 'avoid'
export type TreatmentStatus = 'planned' | 'in_progress' | 'completed' | 'deferred'

export interface RiskAssessment {
  id: number
  likelihood: number       // 1-5
  impact: number           // 1-5
  risk_score: number       // likelihood * impact
  residual_likelihood: number | null
  residual_impact: number | null
  residual_risk_score: number | null
  notes: string | null
  assessed_at: string
}

export interface RiskTreatment {
  id: number
  treatment_type: TreatmentType
  mitigation_strategy: string
  owner_id: number | null
  start_date: string | null
  target_date: string | null
  completion_date: string | null
  status: TreatmentStatus
  cost_estimate: number | null
  notes: string | null
  created_at: string
}

export interface RiskOwnerSummary {
  id: number
  email: string
  full_name: string | null
}

export interface RiskHistory {
  id: number
  field_changed: string
  old_value: string | null
  new_value: string | null
  changed_by_id: number
  changed_at: string
}

export interface Risk {
  id: number
  risk_id: string          // e.g. "RISK-001"
  title: string
  description: string | null
  threat_source: string | null
  threat_event: string | null
  vulnerability: string | null
  affected_asset: string | null
  category: string | null
  status: RiskStatus
  review_frequency_days: number | null
  next_review_date: string | null
  owner_id: number
  owner: RiskOwnerSummary | null
  created_by_id: number
  created_at: string
  updated_at: string | null
  assessments: RiskAssessment[]
  treatments: RiskTreatment[]
  history: RiskHistory[]
}

export interface RiskListResponse {
  total: number
  items: Risk[]
}

export interface RiskCreate {
  title: string
  description?: string
  threat_source?: string
  threat_event?: string
  vulnerability?: string
  affected_asset?: string
  category?: string
  owner_id?: number
  likelihood?: number
  impact?: number
  review_frequency_days?: number
  next_review_date?: string
}

export interface RiskUpdate extends Partial<RiskCreate> {
  status?: RiskStatus
}

// -------------------------------------------------------------------------
// Dashboard
// -------------------------------------------------------------------------

export interface DashboardSummary {
  total: number
  by_status: Record<string, number>
  by_severity: Record<string, number>
  overdue_treatments: number
  overdue_reviews: number
  risk_matrix: number[][]   // [likelihood-1][impact-1] → count
}

export interface ScoreHistoryPoint {
  date: string       // YYYY-MM-DD
  avg_score: number
  count: number
}

export interface ScoreHistoryResponse {
  points: ScoreHistoryPoint[]
}

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

/** Returns the current risk score from the latest assessment, or null. */
export function currentScore(risk: Risk): number | null {
  return risk.assessments[0]?.risk_score ?? null
}

/** Maps a risk score (1-25) to a severity label. */
export function scoreLabel(score: number): 'Low' | 'Medium' | 'High' | 'Critical' {
  if (score <= 5) return 'Low'
  if (score <= 12) return 'Medium'
  if (score <= 20) return 'High'
  return 'Critical'
}

/** Maps a severity label to a Tailwind color class for badges. */
export function scoreBadgeClass(score: number): string {
  const label = scoreLabel(score)
  const map: Record<string, string> = {
    Low:      'bg-green-100 text-green-800',
    Medium:   'bg-yellow-100 text-yellow-800',
    High:     'bg-orange-100 text-orange-800',
    Critical: 'bg-red-100 text-red-800',
  }
  return map[label]
}
