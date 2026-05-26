/**
 * Badge — small inline label for status, severity, categories.
 *
 * Uses class-variance-authority (CVA) to manage variant classes, the same
 * pattern as Button. Add a new variant here when you need a new colour.
 */
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  // Base styles shared across all variants
  'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
  {
    variants: {
      variant: {
        default:  'bg-primary/10 text-primary',
        secondary: 'bg-secondary text-secondary-foreground',
        outline:  'border border-border text-foreground',
        // Risk severity — mapped from score ranges in scoreBadgeVariant() below
        low:      'bg-green-100  text-green-800  dark:bg-green-900/40  dark:text-green-200',
        medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200',
        high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200',
        critical:    'bg-red-100    text-red-800    dark:bg-red-900/40    dark:text-red-200',
        destructive: 'bg-red-100    text-red-800    dark:bg-red-900/40    dark:text-red-200',
        // Risk status
        open:        'bg-blue-100   text-blue-800   dark:bg-blue-900/40   dark:text-blue-200',
        in_progress: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200',
        mitigated:   'bg-green-100  text-green-800  dark:bg-green-900/40  dark:text-green-200',
        accepted:    'bg-gray-100   text-gray-700   dark:bg-gray-800      dark:text-gray-300',
        closed:      'bg-gray-200   text-gray-500   dark:bg-gray-700      dark:text-gray-400',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>['variant']>

interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}

/**
 * Map a numeric risk score (1-25) to the matching Badge variant.
 * Import and use alongside <Badge>:
 *   <Badge variant={scoreToBadgeVariant(score)}>{scoreLabel(score)}</Badge>
 */
export function scoreToBadgeVariant(score: number): BadgeVariant {
  if (score <= 5)  return 'low'
  if (score <= 12) return 'medium'
  if (score <= 20) return 'high'
  return 'critical'
}
