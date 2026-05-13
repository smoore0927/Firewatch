/**
 * Role-gated route. Defaults to admin-only.
 *
 * Wraps child routes in <Outlet />. Renders the children only when the
 * authenticated user's role is included in `roles` (which defaults to
 * ['admin']). Users without a matching role are bounced to /dashboard.
 * While the AuthContext is still resolving the current user, a "Loading..."
 * line is shown -- mirroring ProtectedRoute so the boundary doesn't flash.
 *
 * Compose with ProtectedRoute in App.tsx -- ProtectedRoute handles the
 * "is the user authenticated?" check, this gate handles the role check.
 * Keeping the two concerns separate means each guard remains small.
 *
 * Examples:
 *   <Route element={<AdminRoute />}>          // admin only
 *   <Route element={<AdminRoute roles={['admin', 'security_analyst']} />}>
 */
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import type { UserRole } from '@/types'

interface AdminRouteProps {
  roles?: UserRole[]
}

export default function AdminRoute({ roles = ['admin'] }: Readonly<AdminRouteProps>) {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground text-sm">Loading...</p>
      </div>
    )
  }

  if (!user || !roles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}
