/**
 * Auth gate for protected routes.
 *
 * Renders <Outlet /> (the nested route's page) when the user is authenticated.
 * While AuthContext is still fetching the current user from /api/auth/me,
 * shows a centered loading state so the page doesn't flash to /login and back.
 * Once loading is done, unauthenticated users are redirected to /login.
 *
 * Usage in App.tsx:
 *   <Route element={<ProtectedRoute />}>
 *     <Route element={<AppLayout />}>
 *       <Route path="/dashboard" element={<DashboardPage />} />
 *     </Route>
 *   </Route>
 */
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

export default function ProtectedRoute() {
  const { user, isLoading } = useAuth()

  // AuthContext calls /api/auth/me on mount. Show a spinner until that
  // resolves so we don't redirect authenticated users with a slow cookie check.
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground text-sm">Loading...</p>
      </div>
    )
  }

  // No user after loading completes -- send to login.
  // 'replace' prevents the /login entry from being added to browser history,
  // so pressing Back doesn't loop the user between login and the gate.
  if (!user) {
    return <Navigate to="/login" replace />
  }

  // Authenticated -- render the nested route tree.
  return <Outlet />
}
