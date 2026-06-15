import { useId, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useEscapeKey } from '@/lib/useEscapeKey'

interface ModalProps {
  open: boolean
  onClose: () => void
  /** Optional heading; when set, a header row (title + close button) is rendered. */
  title?: ReactNode
  /** Optional sub-text shown under the title. */
  description?: ReactNode
  children: ReactNode
  /**
   * While true the dialog cannot be dismissed via Escape, backdrop click, or the
   * close button (e.g. mid-submit). Pass the submitting flag here.
   */
  busy?: boolean
  /** Suppress the default header close (X) button even when a title is present. */
  hideClose?: boolean
  /** Extra classes for the panel (defaults to a max-w-lg card). */
  className?: string
}

/**
 * Shared modal shell: backdrop + centered panel + Escape/backdrop dismissal +
 * optional header. Replaces the overlay/escape/close boilerplate that was
 * hand-rolled (and had drifted) across the app's dialogs.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  busy = false,
  hideClose = false,
  className,
}: Readonly<ModalProps>) {
  const titleId = useId()
  const dismiss = () => { if (!busy) onClose() }
  useEscapeKey(dismiss, open)

  if (!open) return null

  const showHeader = title != null || !hideClose

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={dismiss}
    >
      <div
        className={cn('w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg', className)}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title != null ? titleId : undefined}
      >
        {showHeader && (
          <div className="flex items-start justify-between gap-4">
            <div>
              {title != null && (
                <h2 id={titleId} className="text-lg font-semibold">{title}</h2>
              )}
              {description != null && (
                <p className="mt-1 text-sm text-muted-foreground">{description}</p>
              )}
            </div>
            {!hideClose && (
              <button
                type="button"
                onClick={onClose}
                disabled={busy}
                className="text-muted-foreground hover:text-foreground disabled:opacity-50"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
        <div className={cn(showHeader && 'mt-6')}>{children}</div>
      </div>
    </div>
  )
}
