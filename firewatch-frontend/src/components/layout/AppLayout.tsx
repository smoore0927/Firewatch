/**
 * Persistent shell layout rendered for every authenticated page.
 *
 * Structure:
 *   <div class="flex min-h-screen">
 *     <aside>  sidebar: logo, nav links, user info, sign-out
 *     <main>   page content via <Outlet />
 *
 * NavLink from React Router applies an active class automatically when
 * the current URL matches the link's `to` prop, so we get highlighted
 * nav items with no manual tracking.
 *
 * The sidebar is resizable (drag the right edge) and collapsible (chevron
 * button in the brand row). Width and collapsed state persist in
 * localStorage under the key "firewatch.sidebar.main".
 */
import { Outlet, NavLink, useNavigate, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import {
  ShieldAlert,
  LayoutDashboard,
  Activity,
  ShieldCheck,
  LogOut,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useResizableSidebar } from '@/lib/useResizableSidebar'
import { cn } from '@/lib/utils'

const COLLAPSE_THRESHOLD = 140

export default function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const { width, isCollapsed, toggleCollapsed, startResize } = useResizableSidebar({
    storageKey: 'firewatch.sidebar.main',
    defaultWidth: 256,
    minWidth: 64,
    maxWidth: 384,
  })

  const isNarrow = width < COLLAPSE_THRESHOLD

  const location = useLocation()
  if (user?.must_change_password && !location.pathname.startsWith('/settings/password')) {
    return <Navigate to="/settings/password" replace />
  }

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  const navLinkClass = (isActive: boolean) =>
    cn(
      'flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors',
      isNarrow ? 'justify-center' : 'gap-3',
      isActive
        ? 'bg-primary text-primary-foreground'
        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
    )

  return (
    <div className="flex h-screen bg-background">
      {/* ---- Sidebar ---- */}
      <aside
        style={{ width }}
        className="border-r bg-card flex flex-col shrink-0 relative"
      >

        {/* Brand */}
        <div
          className={cn(
            'flex items-center px-4 py-5 border-b',
            isNarrow ? 'justify-center' : 'gap-2 px-6 justify-between',
          )}
        >
          {isNarrow ? (
            <ShieldAlert className="h-6 w-6 text-primary" />
          ) : (
            <div className="flex items-center gap-2 min-w-0">
              <ShieldAlert className="h-6 w-6 text-primary shrink-0" />
              <span className="font-semibold text-lg tracking-tight truncate">Firewatch</span>
            </div>
          )}
          {!isNarrow && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 shrink-0"
              onClick={toggleCollapsed}
              title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
          )}
        </div>

        {isNarrow && (
          <div className="flex justify-center py-2 border-b">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={toggleCollapsed}
              title="Expand sidebar"
              aria-label="Expand sidebar"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 flex flex-col">
          <div className="space-y-1">
            <NavLink
              to="/dashboard"
              title={isNarrow ? 'Dashboard' : undefined}
              className={({ isActive }) => navLinkClass(isActive)}
            >
              <LayoutDashboard className="h-4 w-4 shrink-0" />
              {!isNarrow && <span>Dashboard</span>}
            </NavLink>

            <NavLink
              to="/analytics"
              title={isNarrow ? 'Risk Velocity' : undefined}
              className={({ isActive }) => navLinkClass(isActive)}
            >
              <Activity className="h-4 w-4 shrink-0" />
              {!isNarrow && <span>Risk Velocity</span>}
            </NavLink>

            <NavLink
              to="/risks"
              title={isNarrow ? 'Risk Register' : undefined}
              className={({ isActive }) => navLinkClass(isActive)}
            >
              <ShieldCheck className="h-4 w-4 shrink-0" />
              {!isNarrow && <span>Risk Register</span>}
            </NavLink>

            <NavLink
              to="/settings"
              title={isNarrow ? 'Settings' : undefined}
              className={({ isActive }) => navLinkClass(isActive)}
            >
              <Settings className="h-4 w-4 shrink-0" />
              {!isNarrow && <span>Settings</span>}
            </NavLink>
          </div>
        </nav>

        {/* User info + sign out */}
        <div
          className={cn(
            'border-t py-4 space-y-1',
            isNarrow ? 'px-2 flex flex-col items-center' : 'px-4',
          )}
        >
          {!isNarrow && (
            <>
              <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
              <p className="text-xs font-medium capitalize text-foreground">
                {user?.role.replace('_', ' ')}
              </p>
            </>
          )}
          <Button
            variant="ghost"
            size={isNarrow ? 'icon' : 'sm'}
            className={cn(
              'text-muted-foreground hover:text-foreground',
              isNarrow ? 'mt-0' : 'mt-2 w-full justify-start gap-2',
            )}
            onClick={handleLogout}
            title={isNarrow ? 'Sign out' : undefined}
            aria-label={isNarrow ? 'Sign out' : undefined}
          >
            <LogOut className="h-4 w-4" />
            {!isNarrow && 'Sign out'}
          </Button>
        </div>

        {/* Drag handle */}
        <div
          onMouseDown={startResize}
          className="absolute right-0 top-0 h-full w-1 cursor-col-resize hover:bg-border"
          aria-hidden="true"
        />
      </aside>

      {/* ---- Page content ---- */}
      <main className="flex-1 overflow-y-auto p-8">
        <Outlet />
      </main>
    </div>
  )
}
