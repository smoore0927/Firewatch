import { useState } from 'react'
import { format, parseISO } from 'date-fns'
import { Calendar as CalendarIcon } from 'lucide-react'
import type { DateRange } from 'react-day-picker'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

export type RangePreset = '30d' | '60d' | '90d' | '180d' | '1y' | 'custom'

export function presetDays(p: Exclude<RangePreset, 'custom'>): number {
  return { '30d': 30, '60d': 60, '90d': 90, '180d': 180, '1y': 365 }[p]
}

const PRESET_LABELS: Record<Exclude<RangePreset, 'custom'>, string> = {
  '30d': 'Last 30 days',
  '60d': 'Last 60 days',
  '90d': 'Last 90 days',
  '180d': 'Last 180 days',
  '1y': 'Last 1 year',
}

const PRESET_ORDER: RangePreset[] = ['30d', '60d', '90d', '180d', '1y', 'custom']

function toDateStr(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatCustomRange(start: Date, end: Date): string {
  const sameYear = start.getFullYear() === end.getFullYear()
  const startFmt = sameYear ? format(start, 'MMM d') : format(start, 'MMM d, yyyy')
  const endFmt = format(end, 'MMM d, yyyy')
  return `${startFmt} – ${endFmt}`
}

interface Props {
  start: string
  end: string
  preset: RangePreset
  onChange: (next: { start: string; end: string; preset: RangePreset }) => void
}

export function DateRangePicker({ start, end, preset, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const [pendingRange, setPendingRange] = useState<DateRange | undefined>(undefined)

  const startDate = parseISO(start)
  const endDate = parseISO(end)

  const triggerLabel =
    preset === 'custom'
      ? formatCustomRange(startDate, endDate)
      : PRESET_LABELS[preset]

  function handlePresetClick(p: RangePreset) {
    if (p === 'custom') {
      onChange({ start, end, preset: 'custom' })
      setOpen(false)
      return
    }
    const today = new Date()
    const newStart = new Date(today)
    newStart.setDate(today.getDate() - presetDays(p))
    onChange({ start: toDateStr(newStart), end: toDateStr(today), preset: p })
    setOpen(false)
  }

  function handleCalendarSelect(range: DateRange | undefined) {
    setPendingRange(range)
  }

  function applyPending() {
    if (!pendingRange?.from || !pendingRange.to) return
    onChange({
      start: toDateStr(pendingRange.from),
      end: toDateStr(pendingRange.to),
      preset: 'custom',
    })
    setPendingRange(undefined)
    setOpen(false)
  }

  function cancelPending() {
    setPendingRange(undefined)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) setPendingRange(undefined) }}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex h-8 items-center gap-2 rounded-md border border-input bg-background px-2 text-xs shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <CalendarIcon className="h-3.5 w-3.5 opacity-70" />
          <span>{triggerLabel}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="flex w-auto flex-col gap-2 p-2" onKeyDown={(e) => { if (e.key === 'Enter') applyPending() }}>
        <div className="flex gap-2">
          <div className="flex w-40 flex-col gap-1 border-r border-border pr-2">
            {PRESET_ORDER.map((p) => {
              const label = p === 'custom' ? 'Custom' : PRESET_LABELS[p]
              const active = preset === p
              return (
                <Button
                  key={p}
                  variant="ghost"
                  size="sm"
                  onClick={() => handlePresetClick(p)}
                  className={cn('justify-start text-xs font-normal', active && 'bg-accent text-accent-foreground')}
                >
                  {label}
                </Button>
              )
            })}
          </div>
          <Calendar
            mode="range"
            numberOfMonths={2}
            selected={pendingRange}
            onSelect={handleCalendarSelect}
            defaultMonth={startDate}
          />
        </div>
        {pendingRange?.from && pendingRange.to && (
          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button size="sm" variant="outline" onClick={cancelPending}>Cancel</Button>
            <Button size="sm" onClick={applyPending}>Apply</Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
