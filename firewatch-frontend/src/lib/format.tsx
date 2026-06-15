import type { ReactNode } from 'react'

/**
 * Shared display formatters.
 *
 * These were previously copy-pasted across several pages; keep the single
 * canonical version here so date/truncation rendering stays consistent.
 */

/** Locale date-time string, or a muted em-dash placeholder when null/empty. */
export function formatDate(iso: string | null | undefined): ReactNode {
  if (!iso) return <span className="text-muted-foreground">—</span>
  return new Date(iso).toLocaleString()
}

/** Truncate to at most `max` characters, appending an ellipsis when cut. */
export function truncate(value: string | null | undefined, max = 80): string {
  if (!value) return ''
  if (value.length <= max) return value
  return value.slice(0, max - 1) + '…'
}
