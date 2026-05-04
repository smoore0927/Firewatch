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
        outline:  'border border-border text-foreground',
        // Risk severity — mapped from score ranges in scoreBadgeVariant() below
        low:      'bg-green-100  text-green-800',
        medium:   'bg-yellow-100 text-yellow-800',
        high:     'bg-orange-100 text-orange-800',
        critical:    'bg-red-100    text-red-800',
        destructive: 'bg-red-100    text-red-800',
        // Risk status
        open:        'bg-blue-100  text-blue-800',
        in_progress: 'bg-purple-100 text-purple-800',
        mitigated:   'bg-green-100 text-green-800',
        accepted:    'bg-gray-100  text-gray-700',
        closed:      'bg-gray-200  text-gray-500',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>['variant']>

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
