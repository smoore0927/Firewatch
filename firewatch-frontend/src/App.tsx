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
import { Suspense, lazy } from 'react'
import ProtectedRoute from '@/components/layout/ProtectedRoute'
import AdminRoute from '@/components/layout/AdminRoute'
import AppLayout from '@/components/layout/AppLayout'
import SettingsLayout from '@/components/layout/SettingsLayout'

// Page components are route-level and loaded on demand to keep the initial
// bundle small. The app shell (layouts/route guards above) stays eager so the
// chrome renders instantly while a page chunk streams in.
const LoginPage = lazy(() => import('@/pages/LoginPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const ActionQueuePage = lazy(() => import('@/pages/ActionQueuePage'))
const AnalyticsPage = lazy(() => import('@/pages/AnalyticsPage'))
const RisksPage = lazy(() => import('@/pages/RisksPage'))
const RiskDetailPage = lazy(() => import('@/pages/RiskDetailPage'))
const RiskFormPage = lazy(() => import('@/pages/RiskFormPage'))
const SettingsPasswordPage = lazy(() => import('@/pages/SettingsPasswordPage'))
const SettingsAppearancePage = lazy(() => import('@/pages/SettingsAppearancePage'))
const SettingsUsersPage = lazy(() => import('@/pages/SettingsUsersPage'))
const SettingsApiKeysPage = lazy(() => import('@/pages/SettingsApiKeysPage'))
const SettingsFrameworksPage = lazy(() => import('@/pages/SettingsFrameworksPage'))
const SettingsWebhooksPage = lazy(() => import('@/pages/SettingsWebhooksPage'))
const AuditLogPage = lazy(() => import('@/pages/AuditLogPage'))

export default function App() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-screen">
          <p className="text-muted-foreground text-sm">Loading...</p>
        </div>
      }
    >
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />

      {/* Protected routes -- auth gate wraps the layout shell */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/risks" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/action-queue" element={<ActionQueuePage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/risks" element={<RisksPage />} />
          {/* /risks/new must come before /risks/:riskId so React Router
              doesn't try to load "new" as a risk ID */}
          <Route path="/risks/new" element={<RiskFormPage mode="create" />} />
          <Route path="/risks/:riskId" element={<RiskDetailPage />} />
          <Route path="/risks/:riskId/edit" element={<RiskFormPage mode="edit" />} />

          {/* /account kept as a redirect for backward compatibility */}
          <Route path="/account" element={<Navigate to="/settings/account/password" replace />} />

          <Route path="/settings" element={<SettingsLayout />}>
            <Route index element={<Navigate to="account/password" replace />} />
            <Route path="account">
              <Route index element={<Navigate to="password" replace />} />
              <Route path="password" element={<SettingsPasswordPage />} />
              <Route path="appearance" element={<SettingsAppearancePage />} />
            </Route>
            <Route element={<AdminRoute />}>
              <Route path="users" element={<SettingsUsersPage />} />
              <Route path="webhooks" element={<SettingsWebhooksPage />} />
              <Route path="audit-log" element={<AuditLogPage />} />
            </Route>
            <Route element={<AdminRoute roles={['admin', 'security_analyst']} />}>
              <Route path="api-keys" element={<SettingsApiKeysPage />} />
              <Route path="frameworks" element={<SettingsFrameworksPage />} />
            </Route>
          </Route>
        </Route>
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/risks" replace />} />
    </Routes>
    </Suspense>
  )
}
