/**
 * Route map for the entire application.
 *
 * Route layout (read top to bottom):
 *
 *   /login              -- public, no auth required
 *   <ProtectedRoute>    -- redirects to /login if not authenticated
 *     <AppLayout>       -- renders sidebar + header shell; page fills <Outlet>
 *       /               -- redirects to /dashboard
 *       /dashboard      -- risk register overview
 *   *                   -- catch-all redirects to /dashboard
 *
 * Why nest ProtectedRoute around AppLayout?
 *   ProtectedRoute handles the auth gate. AppLayout handles the chrome
 *   (sidebar, header). Separating them means we can later add public pages
 *   that still use a layout, without repeating the auth check.
 */
import { Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from '@/components/layout/ProtectedRoute'
import AdminRoute from '@/components/layout/AdminRoute'
import AppLayout from '@/components/layout/AppLayout'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import RisksPage from '@/pages/RisksPage'
import RiskDetailPage from '@/pages/RiskDetailPage'
import RiskFormPage from '@/pages/RiskFormPage'
import SettingsPage from '@/pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />

      {/* Protected routes -- auth gate wraps the layout shell */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/risks" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/risks" element={<RisksPage />} />
          {/* /risks/new must come before /risks/:riskId so React Router
              doesn't try to load "new" as a risk ID */}
          <Route path="/risks/new" element={<RiskFormPage mode="create" />} />
          <Route path="/risks/:riskId" element={<RiskDetailPage />} />
          <Route path="/risks/:riskId/edit" element={<RiskFormPage mode="edit" />} />

          {/* Admin-only settings — AdminRoute redirects non-admins to /dashboard. */}
          <Route element={<AdminRoute />}>
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Route>
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/risks" replace />} />
    </Routes>
  )
}
