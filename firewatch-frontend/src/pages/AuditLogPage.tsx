/**
 * Audit log page (admin-only — gated by AdminRoute in App.tsx).
 *
 * Rendered as a nested route under /settings via SettingsLayout, which
 * provides the outer "Settings" heading and side nav. This page just
 * renders the audit log table itself.
 */
import AuditLogPanel from '@/components/settings/AuditLogPanel'

export default function AuditLogPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Audit log</h2>
        <p className="text-muted-foreground text-sm">Administrative history of system events.</p>
      </div>

      <AuditLogPanel />
    </div>
  )
}
