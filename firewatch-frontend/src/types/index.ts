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
  has_password: boolean
  must_change_password: boolean
  is_active: boolean
  created_at: string
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
  has_password: boolean
  must_change_password: boolean
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

export type ResponseType = 'mitigate' | 'accept' | 'transfer' | 'avoid'
export type ResponseStatus = 'planned' | 'in_progress' | 'completed' | 'deferred'

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

export interface RiskResponse {
  id: number
  response_type: ResponseType
  mitigation_strategy: string
  owner_id: number | null
  start_date: string | null
  target_date: string | null
  completion_date: string | null
  status: ResponseStatus
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
  responses: RiskResponse[]
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

export interface ImportResultRow {
  row: number
  message: string
}

export interface ImportResult {
  created: number
  errors: ImportResultRow[]
}

// -------------------------------------------------------------------------
// Dashboard
// -------------------------------------------------------------------------

export interface DashboardSummary {
  total: number
  by_status: Record<string, number>
  by_severity: Record<string, number>
  overdue_responses: number
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

// Lowercase severity key form used by the score-totals-by-severity API.
// Distinct from RiskSeverity (title-case) used in report rows.
export type Severity = 'low' | 'medium' | 'high' | 'critical'

export interface ScoreTotalsBySeverityPoint {
  date: string
  low: number
  medium: number
  high: number
  critical: number
}

export interface ScoreTotalsBySeverityResponse {
  points: ScoreTotalsBySeverityPoint[]
}

// -------------------------------------------------------------------------
// Analytics
// -------------------------------------------------------------------------

export interface VelocityMTTMBySeverity {
  critical: number | null
  high: number | null
  medium: number | null
  low: number | null
}

export interface VelocityMTTMResponse {
  mean_days: number | null
  median_days: number | null
  count: number
  by_severity: VelocityMTTMBySeverity
}

export interface VelocityThroughputPoint {
  period: string   // "YYYY-MM"
  opened: number
  closed: number
}

export interface VelocityThroughputResponse {
  points: VelocityThroughputPoint[]
}

export interface ResidualReductionBySeverity {
  critical: number | null
  high: number | null
  medium: number | null
  low: number | null
}

export interface ResidualReductionResponse {
  avg_absolute: number | null
  avg_percentage: number | null
  count: number
  by_severity: ResidualReductionBySeverity
}

// -------------------------------------------------------------------------
// Reports
// -------------------------------------------------------------------------

export type RiskSeverity = 'Low' | 'Medium' | 'High' | 'Critical' | 'Unscored'

export interface RiskReportRow {
  id: number
  title: string
  category: string | null
  status: string
  current_likelihood: number | null
  current_impact: number | null
  current_score: number | null
  severity: RiskSeverity
  owner_name: string | null
  next_review_date: string | null
}

export interface RiskReport {
  generated_at: string
  generated_by: {
    id: number
    email: string
    full_name: string | null
    role: string
  }
  date_range: {
    start: string
    end: string
  }
  summary: DashboardSummary
  score_history: ScoreHistoryResponse
  risks: RiskReportRow[] | null
}

// -------------------------------------------------------------------------
// Audit
// -------------------------------------------------------------------------

export interface AuditLog {
  id: number
  user_id: number | null
  user_email: string | null
  action: string
  resource_type: string | null
  resource_id: string | null
  ip_address: string | null
  user_agent: string | null
  details: string | null
  created_at: string
}

export interface AuditLogListResponse {
  total: number
  items: AuditLog[]
}

// -------------------------------------------------------------------------
// API keys
// -------------------------------------------------------------------------

export interface ApiKey {
  id: number
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
  expires_at: string | null
  revoked_at: string | null
}

export interface ApiKeyCreated extends ApiKey {
  key: string
}

export interface ApiKeyOwnerSummary {
  id: number
  email: string
  full_name: string | null
}

export interface ApiKeyWithOwner extends ApiKey {
  owner: ApiKeyOwnerSummary
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
