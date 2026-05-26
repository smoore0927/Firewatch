import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, X } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { notificationsApi } from '@/services/api'
import type { NotificationItem } from '@/types'
import { cn } from '@/lib/utils'

const UNREAD_POLL_MS = 60_000
const LIST_CACHE_MS = 30_000

function formatRelative(iso: string): string {
  const ts = new Date(iso).getTime()
  if (Number.isNaN(ts)) return ''
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000))
  if (diffSec < 60) return 'just now'
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  if (diffDay < 7) return `${diffDay}d ago`
  const diffWk = Math.floor(diffDay / 7)
  if (diffWk < 5) return `${diffWk}w ago`
  return new Date(iso).toLocaleDateString()
}

export default function NotificationBell() {
  const navigate = useNavigate()
  const [unreadCount, setUnreadCount] = useState(0)
  const [items, setItems] = useState<NotificationItem[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const lastFetchedAt = useRef(0)

  // Poll the unread count on mount and every 60 seconds while the component
  // is mounted. Standard useEffect cleanup handles StrictMode double-mount.
  useEffect(() => {
    let cancelled = false

    const tick = async () => {
      try {
        const { count } = await notificationsApi.unreadCount()
        if (!cancelled) setUnreadCount(count)
      } catch {
        // Silent — bell stays at last known count if the request fails.
      }
    }

    tick()
    const id = setInterval(tick, UNREAD_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  const loadList = useCallback(async (force = false) => {
    const now = Date.now()
    if (!force && now - lastFetchedAt.current < LIST_CACHE_MS && items.length > 0) {
      return
    }
    setIsLoading(true)
    try {
      const res = await notificationsApi.list({ limit: 20 })
      setItems(res.items)
      setUnreadCount(res.unread_total)
      lastFetchedAt.current = Date.now()
    } catch {
      // Leave previous items in place on error.
    } finally {
      setIsLoading(false)
    }
  }, [items.length])

  function handleOpenChange(open: boolean) {
    setIsOpen(open)
    if (open) {
      void loadList()
    }
  }

  async function handleMarkAllRead() {
    if (unreadCount === 0) return
    const prevUnread = unreadCount
    const prevItems = items
    setUnreadCount(0)
    setItems(items.map((n) => (n.read_at ? n : { ...n, read_at: new Date().toISOString() })))
    try {
      await notificationsApi.markAllRead()
      lastFetchedAt.current = 0
      void loadList(true)
    } catch {
      setUnreadCount(prevUnread)
      setItems(prevItems)
    }
  }

  async function handleRowClick(n: NotificationItem) {
    setIsOpen(false)
    if (!n.read_at) {
      setItems((prev) =>
        prev.map((item) =>
          item.id === n.id ? { ...item, read_at: new Date().toISOString() } : item,
        ),
      )
      setUnreadCount((c) => Math.max(0, c - 1))
      notificationsApi.markRead(n.id).catch(() => undefined)
    }
    navigate(n.link)
  }

  async function handleMarkRowRead(e: React.MouseEvent, n: NotificationItem) {
    e.stopPropagation()
    e.preventDefault()
    if (n.read_at) return
    setItems((prev) =>
      prev.map((item) =>
        item.id === n.id ? { ...item, read_at: new Date().toISOString() } : item,
      ),
    )
    setUnreadCount((c) => Math.max(0, c - 1))
    try {
      await notificationsApi.markRead(n.id)
    } catch {
      // Optimistic update only — the next poll will reconcile.
    }
  }

  const badgeLabel = unreadCount > 9 ? '9+' : String(unreadCount)

  return (
    <DropdownMenu open={isOpen} onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={
            unreadCount > 0
              ? `Notifications (${unreadCount} unread)`
              : 'Notifications'
          }
          className="relative inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <span
              data-testid="notification-badge"
              className="absolute -top-0.5 -right-0.5 min-w-[1.125rem] h-[1.125rem] px-1 flex items-center justify-center rounded-full bg-red-600 text-[10px] font-semibold leading-none text-white"
            >
              {badgeLabel}
            </span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={8}
        className="w-[360px] p-0 bg-white dark:bg-gray-900 text-popover-foreground"
      >
        <div className="flex items-center justify-between border-b px-4 py-2.5">
          <span className="text-sm font-semibold">Notifications</span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            disabled={unreadCount === 0}
            onClick={handleMarkAllRead}
          >
            Mark all read
          </Button>
        </div>

        <div className="max-h-[480px] overflow-y-auto">
          {isLoading && items.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground">
              Loading…
            </div>
          ) : items.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground">
              You&apos;re all caught up.
            </div>
          ) : (
            <ul className="divide-y">
              {items.map((n) => {
                const isUnread = !n.read_at
                return (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => handleRowClick(n)}
                      className={cn(
                        'group relative w-full text-left px-4 py-3 hover:bg-accent/60 transition-colors',
                        isUnread && 'bg-accent/40 border-l-2 border-blue-500',
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-semibold truncate flex-1">
                          {n.title}
                        </p>
                        <span className="text-[11px] text-muted-foreground shrink-0">
                          {formatRelative(n.created_at)}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2 pr-6">
                        {n.message}
                      </p>
                      {isUnread && (
                        <span
                          role="button"
                          tabIndex={0}
                          aria-label={`Mark "${n.title}" as read`}
                          onClick={(e) => handleMarkRowRead(e, n)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault()
                              handleMarkRowRead(e as unknown as React.MouseEvent, n)
                            }
                          }}
                          className="absolute right-2 top-2 hidden group-hover:inline-flex items-center justify-center h-5 w-5 rounded text-muted-foreground hover:bg-background hover:text-foreground"
                        >
                          <X className="h-3 w-3" />
                        </span>
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
