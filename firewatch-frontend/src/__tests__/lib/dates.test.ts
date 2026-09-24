import { afterEach, describe, expect, it, vi } from 'vitest'
import { calendarDay, formatCalendarDate, toLocalISODate, todayLocalISODate } from '@/lib/dates'

// Expected values are built with local-time constructors, so these hold in any
// timezone — and fail against the old UTC parsing anywhere off UTC.
describe('calendar-date helpers', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('formats a date-only value as that calendar day', () => {
    // new Date('2026-10-07') is UTC midnight: still Oct 6 west of Greenwich.
    expect(formatCalendarDate('2026-10-07')).toBe(new Date(2026, 9, 7).toLocaleDateString())
  })

  it('reads the day from the UTC-midnight datetimes used for response dates', () => {
    expect(calendarDay('2026-11-30T00:00:00+00:00')).toBe('2026-11-30')
    expect(formatCalendarDate('2026-11-30T00:00:00+00:00')).toBe(
      new Date(2026, 10, 30).toLocaleDateString(),
    )
  })

  it("uses the local date for today at both ends of the day", () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    // Late evening: already tomorrow in UTC for anyone west of Greenwich.
    vi.setSystemTime(new Date(2026, 8, 22, 21, 30))
    expect(todayLocalISODate()).toBe('2026-09-22')
    // Just after midnight: still yesterday in UTC for anyone east of it.
    vi.setSystemTime(new Date(2026, 8, 22, 0, 30))
    expect(todayLocalISODate()).toBe('2026-09-22')
  })

  it('zero-pads months and days', () => {
    expect(toLocalISODate(new Date(2026, 0, 5))).toBe('2026-01-05')
  })
})
