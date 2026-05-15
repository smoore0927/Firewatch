export const CATEGORIES = [
  'Technical',
  'Compliance',
  'Operational',
  'Strategic',
  'Financial',
  'Reputational',
] as const

export type Category = (typeof CATEGORIES)[number]
