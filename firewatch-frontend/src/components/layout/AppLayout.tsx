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
 * The sidebar will grow as we add more pages (risks list, users, reports).
 * Add new <NavLink> entries inside the <nav> block below.
 */
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { ShieldAlert, LayoutDashboard, ShieldCheck, LogOut } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-screen bg-background">
      {/* ---- Sidebar ---- */}
      <aside className="w-64 border-r bg-card flex flex-col shrink-0">

        {/* Brand */}
        <div className="flex items-center gap-2 px-6 py-5 border-b">
          <ShieldAlert className="h-6 w-6 text-primary" />
          <span className="font-semibold text-lg tracking-tight">Firewatch</span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          <NavLink
            to="/dashboard"
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              }`
            }
          >
            <LayoutDashboard className="h-4 w-4 shrink-0" />
            Dashboard
          </NavLink>

          <NavLink
            to="/risks"
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              }`
            }
          >
            <ShieldCheck className="h-4 w-4 shrink-0" />
            Risk Register
          </NavLink>

          {/* Users and Reports links added in later tasks */}
        </nav>

        {/* User info + sign out */}
        <div className="border-t px-4 py-4 space-y-1">
          <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
          <p className="text-xs font-medium capitalize text-foreground">{user?.role.replace('_', ' ')}</p>
          <Button
            variant="ghost"
            size="sm"
            className="mt-2 w-full justify-start gap-2 text-muted-foreground hover:text-foreground"
            onClick={handleLogout}
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
      </aside>

      {/* ---- Page content ---- */}
      <main className="flex-1 overflow-y-auto p-8">
        <Outlet />
      </main>
    </div>
  )
}
