import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * cn() -- combine Tailwind class names safely.
 *
 * clsx handles conditional classes: cn('base', isActive && 'active')
 * twMerge resolves conflicts: cn('px-2 px-4') => 'px-4' (last wins)
 *
 * Used by every shadcn/ui component and throughout the app.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
