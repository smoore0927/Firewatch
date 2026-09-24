/**
 * Calendar-date helpers.
 *
 * Date-only values — a risk's next_review_date, a response's target and
 * completion dates — are calendar days, not instants. Two easy mistakes shift
 * them by a day for anyone west of UTC:
 *   - `new Date('2026-10-07')` parses as UTC midnight, which is still Oct 6
 *     in New York, so it renders as 10/6/2026.
 *   - `new Date().toISOString().slice(0, 10)` is today's *UTC* date, which is
 *     already tomorrow on a US evening.
 * Route date-only values and "today" through these helpers instead.
 */

/** The local calendar date of `d`, as YYYY-MM-DD. */
export function toLocalISODate(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** Today's local calendar date, as YYYY-MM-DD. */
export function todayLocalISODate(): string {
  return toLocalISODate(new Date())
}

/**
 * The calendar day of a date-only API value, as YYYY-MM-DD. Accepts plain dates
 * ("2026-10-07") and the UTC-midnight datetimes the API returns for response
 * dates ("2026-10-07T00:00:00+00:00"). Comparable as strings.
 */
export function calendarDay(value: string): string {
  return value.slice(0, 10)
}

/** Locale display of a date-only API value, e.g. "10/7/2026", with no day shift. */
export function formatCalendarDate(value: string): string {
  const [year, month, day] = calendarDay(value).split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString()
}
