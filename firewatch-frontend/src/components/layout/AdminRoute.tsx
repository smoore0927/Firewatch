/**
 * Admin-only route gate.
 *
 * Wraps child routes in <Outlet />. Renders the children only when the
 * authenticated user has role === 'admin'. Non-admins are bounced to
 * /dashboard. While the AuthContext is still resolving the current user,
 * a "Loading..." line is shown -- mirroring ProtectedRoute so the boundary
 * doesn't flash.
 *
 * Compose with ProtectedRoute in App.tsx -- ProtectedRoute handles the
 * "is the user authenticated?" check, AdminRoute handles "is the user an
 * admin?". Keeping the two concerns separate means each guard remains small.
 */
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

export default function AdminRoute() {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground text-sm">Loading...</p>
      </div>
    )
  }

  if (user?.role !== 'admin') {
    return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}
