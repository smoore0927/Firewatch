import * as React from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { DayPicker, getDefaultClassNames } from 'react-day-picker'
import 'react-day-picker/style.css'

import { cn } from '@/lib/utils'
import { buttonVariants } from '@/components/ui/button'

export type CalendarProps = React.ComponentProps<typeof DayPicker>

function CalendarChevron({ orientation, className, ...props }: React.ComponentPropsWithoutRef<'svg'> & { orientation?: string }) {
  if (orientation === 'right') {
    return <ChevronRight className={cn('h-4 w-4', className)} {...props} />
  }
  return <ChevronLeft className={cn('h-4 w-4', className)} {...props} />
}

function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  components,
  ...props
}: CalendarProps) {
  const defaultClassNames = getDefaultClassNames()

  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn('p-3', className)}
      classNames={{
        root: cn('w-fit', defaultClassNames.root),
        months: cn('relative flex flex-col gap-4 sm:flex-row sm:gap-6', defaultClassNames.months),
        month: cn('flex flex-col gap-3', defaultClassNames.month),
        month_caption: cn(
          'relative flex h-8 items-center justify-center px-8 text-sm font-medium',
          defaultClassNames.month_caption,
        ),
        caption_label: cn('text-sm font-medium', defaultClassNames.caption_label),
        nav: cn(
          'absolute inset-x-0 top-0 z-20 flex items-center justify-between px-1',
          defaultClassNames.nav,
        ),
        button_previous: cn(
          buttonVariants({ variant: 'ghost' }),
          'h-7 w-7 p-0 opacity-70 hover:opacity-100',
          defaultClassNames.button_previous,
        ),
        button_next: cn(
          buttonVariants({ variant: 'ghost' }),
          'h-7 w-7 p-0 opacity-70 hover:opacity-100',
          defaultClassNames.button_next,
        ),
        month_grid: cn('w-full border-collapse', defaultClassNames.month_grid),
        weekdays: cn('flex', defaultClassNames.weekdays),
        weekday: cn(
          'w-9 flex-1 text-center text-[0.75rem] font-normal text-muted-foreground',
          defaultClassNames.weekday,
        ),
        week: cn('mt-1 flex w-full', defaultClassNames.week),
        day: cn(
          'relative h-9 w-9 flex-1 p-0 text-center text-sm focus-within:relative focus-within:z-20',
          defaultClassNames.day,
        ),
        day_button: cn(
          buttonVariants({ variant: 'ghost' }),
          'h-9 w-9 p-0 font-normal aria-selected:opacity-100',
          defaultClassNames.day_button,
        ),
        range_start: cn(
          'rounded-l-md bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground',
          defaultClassNames.range_start,
        ),
        range_middle: cn(
          'rounded-none bg-accent text-accent-foreground hover:bg-accent hover:text-accent-foreground',
          defaultClassNames.range_middle,
        ),
        range_end: cn(
          'rounded-r-md bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground',
          defaultClassNames.range_end,
        ),
        selected: cn(
          'bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground focus:bg-primary focus:text-primary-foreground',
          defaultClassNames.selected,
        ),
        today: cn(
          'rounded-md bg-accent text-accent-foreground',
          defaultClassNames.today,
        ),
        outside: cn(
          'text-muted-foreground opacity-50 aria-selected:bg-accent/50 aria-selected:text-muted-foreground aria-selected:opacity-30',
          defaultClassNames.outside,
        ),
        disabled: cn('text-muted-foreground opacity-50', defaultClassNames.disabled),
        hidden: cn('invisible', defaultClassNames.hidden),
        ...classNames,
      }}
      components={{
        Chevron: CalendarChevron,
        ...components,
      }}
      {...props}
    />
  )
}
Calendar.displayName = 'Calendar'

export { Calendar }
