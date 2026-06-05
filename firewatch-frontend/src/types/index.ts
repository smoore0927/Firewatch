/**
 * Frontend type re-exports.
 *
 * The bulk of these types are generated from the backend's OpenAPI schema
 * (see `openapi.json` + `npm run generate:types`). This file is a thin shim
 * that re-exports them under the names the rest of the frontend already uses,
 * so consumers can keep importing from `@/types` unchanged.
 *
 * The handful of frontend-only literal unions and helper functions at the
 * bottom of the file have no backend equivalent and stay hand-written.
 */

import type { components } from './generated'

// -------------------------------------------------------------------------
// Auth
// -------------------------------------------------------------------------

export type LoginRequest = components['schemas']['LoginRequest']
export type LoginResponse = components['schemas']['LoginResponse']

// -------------------------------------------------------------------------
// Users
// -------------------------------------------------------------------------

export type UserRole = components['schemas']['UserRole']
export type User = components['schemas']['UserResponse']

// -------------------------------------------------------------------------
// Risks
// -------------------------------------------------------------------------

export type RiskStatus = components['schemas']['RiskStatus']
export type ResponseType = components['schemas']['ResponseType']
export type ResponseStatus = components['schemas']['ResponseStatus']

export type RiskAssessment = components['schemas']['AssessmentResponse']
export type RiskResponse = components['schemas']['ResponseOut']
export type ResponseCreate = components['schemas']['ResponseCreate']
export type ResponseUpdate = components['schemas']['ResponseUpdate']
export type RiskOwnerSummary = components['schemas']['RiskOwnerSummary']
export type RiskHistory = components['schemas']['HistoryResponse']
export type Risk = components['schemas']['RiskResponse']
export type RiskListResponse = components['schemas']['RiskListResponse']
export type RiskCreate = components['schemas']['RiskCreate']
export type RiskUpdate = components['schemas']['RiskUpdate']

export type ImportResultRow = components['schemas']['ImportResultRow']
export type ImportResult = components['schemas']['ImportResult']

// -------------------------------------------------------------------------
// Control frameworks
// -------------------------------------------------------------------------

export type ControlFramework = components['schemas']['ControlFrameworkResponse']
export type Control = components['schemas']['ControlResponse']
export type ControlFamily = components['schemas']['ControlFamilyResponse']
export type FrameworkImportResult = components['schemas']['FrameworkImportResult']
export type FrameworkImportUrlRequest = components['schemas']['FrameworkImportUrlRequest']
export type FrameworkUpdateRequest = { name?: string; version?: string; description?: string }
export type RiskControlMapping = components['schemas']['RiskControlResponse']
export type RiskControlCreate = components['schemas']['RiskControlCreate']

export type BulkReassignRequest = components['schemas']['BulkReassignRequest']
export type BulkStatusRequest = components['schemas']['BulkStatusRequest']
export type BulkRescoreRequest = components['schemas']['BulkRescoreRequest']
export type BulkRiskError = components['schemas']['BulkRiskError']
export type BulkRiskResult = components['schemas']['BulkRiskResult']

// -------------------------------------------------------------------------
// Dashboard
// -------------------------------------------------------------------------

export type DashboardSummary = components['schemas']['DashboardSummaryResponse']
export type ScoreHistoryPoint = components['schemas']['ScoreHistoryPoint']
export type ScoreHistoryResponse = components['schemas']['ScoreHistoryResponse']
export type ScoreTotalsBySeverityPoint = components['schemas']['ScoreTotalsBySeverityPoint']
export type ScoreTotalsBySeverityResponse = components['schemas']['ScoreTotalsBySeverityResponse']
export type ActionQueueItem = components['schemas']['ActionQueueItem']
export type ActionQueueResponse = components['schemas']['ActionQueueResponse']

// -------------------------------------------------------------------------
// Analytics
// -------------------------------------------------------------------------

export type VelocityMTTMBySeverity = components['schemas']['VelocityMTTMBySeverity']
export type VelocityMTTMResponse = components['schemas']['VelocityMTTMResponse']
export type VelocityThroughputPoint = components['schemas']['VelocityThroughputPoint']
export type VelocityThroughputResponse = components['schemas']['VelocityThroughputResponse']
export type ResidualReductionBySeverity = components['schemas']['ResidualReductionBySeverity']
export type ResidualReductionResponse = components['schemas']['ResidualReductionResponse']

// -------------------------------------------------------------------------
// Reports
// -------------------------------------------------------------------------

export type RiskReportRow = components['schemas']['RiskReportRow']
export type RiskReport = components['schemas']['RiskReportResponse']

// -------------------------------------------------------------------------
// Audit
// -------------------------------------------------------------------------

export type AuditLog = components['schemas']['AuditLogResponse']
export type AuditLogListResponse = components['schemas']['AuditLogListResponse']

// -------------------------------------------------------------------------
// API keys
// -------------------------------------------------------------------------

export type ApiKey = components['schemas']['ApiKeyResponse']
export type ApiKeyCreated = components['schemas']['ApiKeyCreatedResponse']
export type ApiKeyOwnerSummary = components['schemas']['ApiKeyOwnerSummary']
export type ApiKeyWithOwner = components['schemas']['ApiKeyWithOwnerResponse']

// -------------------------------------------------------------------------
// Notifications
// -------------------------------------------------------------------------

// `Notification` is a global DOM type, so we expose the row schema as
// `NotificationItem` to avoid shadowing it across the app.
export type NotificationItem = components['schemas']['NotificationResponse']
export type NotificationListResponse = components['schemas']['NotificationListResponse']
export type UnreadCountResponse = components['schemas']['UnreadCountResponse']
export type MarkAllReadResponse = components['schemas']['MarkAllReadResponse']
export type NotificationType = components['schemas']['NotificationType']

// -------------------------------------------------------------------------
// Webhooks
// -------------------------------------------------------------------------

export type WebhookSubscription = components['schemas']['WebhookSubscriptionResponse']
export type WebhookSubscriptionCreated = components['schemas']['WebhookSubscriptionCreatedResponse']
export type WebhookSubscriptionCreate = components['schemas']['WebhookSubscriptionCreate']
export type WebhookSubscriptionUpdate = components['schemas']['WebhookSubscriptionUpdate']
export type WebhookDelivery = components['schemas']['WebhookDeliveryResponse']
export type WebhookDeliveryList = components['schemas']['WebhookDeliveryListResponse']
export type WebhookEventType = 'risk.assigned' | 'review.overdue' | 'response.overdue' | 'firewatch.test'

// -------------------------------------------------------------------------
// Frontend-only types (no backend equivalent)
// -------------------------------------------------------------------------

// Severity is a frontend-only query-param literal — backend exposes it inline on
// each analytics endpoint, not as a reusable component schema.
export type Severity = 'low' | 'medium' | 'high' | 'critical'

export type RiskSeverity = components['schemas']['RiskReportRow']['severity']

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

/** Returns the current risk score from the latest assessment, or null. */
export function currentScore(risk: Risk): number | null {
  const a = risk.assessments[0]
  if (!a) return null
  return a.residual_risk_score ?? a.risk_score
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
    Low:      'bg-green-100  text-green-800  dark:bg-green-900/40  dark:text-green-200',
    Medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200',
    High:     'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200',
    Critical: 'bg-red-100    text-red-800    dark:bg-red-900/40    dark:text-red-200',
  }
  return map[label]
}

/** Formats a likelihood/impact pair consistently as "L × I" using the proper × glyph. Order is always likelihood first, impact second. */
export function formatLikelihoodImpact(likelihood: number, impact: number): string {
  return `${likelihood} × ${impact}`
}
