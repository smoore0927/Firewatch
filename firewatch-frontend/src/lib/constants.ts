import type { RiskStatus } from '@/types'

export const CATEGORIES = [
  'Technical',
  'Compliance',
  'Operational',
  'Strategic',
  'Financial',
  'Reputational',
] as const

export type Category = (typeof CATEGORIES)[number]

/** Human-readable labels for each risk status. Single source of truth. */
export const RISK_STATUS_LABELS: Record<RiskStatus, string> = {
  open:        'Open',
  in_progress: 'In Progress',
  mitigated:   'Mitigated',
  accepted:    'Accepted',
  closed:      'Closed',
}
