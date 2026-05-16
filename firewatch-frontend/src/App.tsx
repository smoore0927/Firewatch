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
import SettingsLayout from '@/components/layout/SettingsLayout'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import AnalyticsPage from '@/pages/AnalyticsPage'
import RisksPage from '@/pages/RisksPage'
import RiskDetailPage from '@/pages/RiskDetailPage'
import RiskFormPage from '@/pages/RiskFormPage'
import SettingsPasswordPage from '@/pages/SettingsPasswordPage'
import SettingsUsersPage from '@/pages/SettingsUsersPage'
import SettingsApiKeysPage from '@/pages/SettingsApiKeysPage'
import SettingsWebhooksPage from '@/pages/SettingsWebhooksPage'
import AuditLogPage from '@/pages/AuditLogPage'

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
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/risks" element={<RisksPage />} />
          {/* /risks/new must come before /risks/:riskId so React Router
              doesn't try to load "new" as a risk ID */}
          <Route path="/risks/new" element={<RiskFormPage mode="create" />} />
          <Route path="/risks/:riskId" element={<RiskDetailPage />} />
          <Route path="/risks/:riskId/edit" element={<RiskFormPage mode="edit" />} />

          {/* /account kept as a redirect for backward compatibility */}
          <Route path="/account" element={<Navigate to="/settings/password" replace />} />

          <Route path="/settings" element={<SettingsLayout />}>
            <Route index element={<Navigate to="password" replace />} />
            <Route path="password" element={<SettingsPasswordPage />} />
            <Route element={<AdminRoute />}>
              <Route path="users" element={<SettingsUsersPage />} />
              <Route path="webhooks" element={<SettingsWebhooksPage />} />
              <Route path="audit-log" element={<AuditLogPage />} />
            </Route>
            <Route element={<AdminRoute roles={['admin', 'security_analyst']} />}>
              <Route path="api-keys" element={<SettingsApiKeysPage />} />
            </Route>
          </Route>
        </Route>
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/risks" replace />} />
    </Routes>
  )
}
