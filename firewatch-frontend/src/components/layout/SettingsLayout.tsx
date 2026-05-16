/**
 * Settings shell with a left sub-nav and a main content area for nested
 * settings pages. The sub-nav lists the user-accessible settings pages —
 * "Change password" is shown to every authenticated user, "Audit log"
 * only to admins (the route itself is also gated by AdminRoute).
 *
 * The sub-nav is resizable (drag the right edge) and collapsible (chevron
 * button next to the heading). Width and collapsed state persist in
 * localStorage under the key "firewatch.sidebar.settings".
 *
 * Nested route children render via <Outlet />.
 */
import { Outlet, NavLink } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { KeyRound, Key, ScrollText, UserCog, Webhook, ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useResizableSidebar } from '@/lib/useResizableSidebar'
import { cn } from '@/lib/utils'

const COLLAPSE_THRESHOLD = 120

export default function SettingsLayout() {
  const { user } = useAuth()

  const { width, isCollapsed, toggleCollapsed, startResize } = useResizableSidebar({
    storageKey: 'firewatch.sidebar.settings',
    defaultWidth: 224,
    minWidth: 56,
    maxWidth: 320,
  })

  const isNarrow = width < COLLAPSE_THRESHOLD

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors',
      isNarrow ? 'justify-center' : 'gap-3',
      isActive
        ? 'bg-primary text-primary-foreground'
        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
    )

  return (
    <div className="flex gap-8">
      <aside style={{ width }} className="shrink-0 relative pr-2">
        <div
          className={cn(
            'flex items-center mb-4',
            isNarrow ? 'justify-center' : 'justify-between gap-2',
          )}
        >
          {!isNarrow && (
            <h1 className="text-2xl font-bold tracking-tight truncate">Settings</h1>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            onClick={toggleCollapsed}
            title={isCollapsed ? 'Expand settings nav' : 'Collapse settings nav'}
            aria-label={isCollapsed ? 'Expand settings nav' : 'Collapse settings nav'}
          >
            {isCollapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </Button>
        </div>

        <nav className="space-y-1">
          <NavLink
            to="/settings/password"
            title={isNarrow ? 'Change password' : undefined}
            className={linkClass}
          >
            <KeyRound className="h-4 w-4 shrink-0" />
            {!isNarrow && <span>Change password</span>}
          </NavLink>

          {(user?.role === 'admin' || user?.role === 'security_analyst') && (
            <NavLink
              to="/settings/api-keys"
              title={isNarrow ? 'API keys' : undefined}
              className={linkClass}
            >
              <Key className="h-4 w-4 shrink-0" />
              {!isNarrow && <span>API keys</span>}
            </NavLink>
          )}

          {user?.role === 'admin' && (
            <NavLink
              to="/settings/webhooks"
              title={isNarrow ? 'Webhooks' : undefined}
              className={linkClass}
            >
              <Webhook className="h-4 w-4 shrink-0" />
              {!isNarrow && <span>Webhooks</span>}
            </NavLink>
          )}

          {user?.role === 'admin' && (
            <NavLink
              to="/settings/users"
              title={isNarrow ? 'Users' : undefined}
              className={linkClass}
            >
              <UserCog className="h-4 w-4 shrink-0" />
              {!isNarrow && <span>Users</span>}
            </NavLink>
          )}

          {user?.role === 'admin' && (
            <NavLink
              to="/settings/audit-log"
              title={isNarrow ? 'Audit log' : undefined}
              className={linkClass}
            >
              <ScrollText className="h-4 w-4 shrink-0" />
              {!isNarrow && <span>Audit log</span>}
            </NavLink>
          )}
        </nav>

        {/* Drag handle */}
        <div
          onMouseDown={startResize}
          className="absolute right-0 top-0 h-full w-1 cursor-col-resize hover:bg-border"
          aria-hidden="true"
        />
      </aside>

      <div className="flex-1 min-w-0">
        <Outlet />
      </div>
    </div>
  )
}
