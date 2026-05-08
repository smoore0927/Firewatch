/**
 * Settings page (admin-only — gated by AdminRoute in App.tsx).
 *
 * The tab strip is built from a small `TABS` array so adding future tabs
 * (e.g. SSO config, integrations) is just a matter of appending an entry
 * with an `id`, `label`, and `panel` component. The current tab id is held
 * in local state and the matching panel is rendered below the strip.
 */
import { useState } from 'react'
import AuditLogPanel from '@/components/settings/AuditLogPanel'

type TabId = 'audit'

interface TabDef {
  id: TabId
  label: string
  panel: React.ReactNode
}

const TABS: TabDef[] = [
  { id: 'audit', label: 'Audit Log', panel: <AuditLogPanel /> },
]

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>('audit')

  const active = TABS.find((t) => t.id === activeTab) ?? TABS[0]

  return (
    <div className="space-y-6">

      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground text-sm">Administrative tools and audit history.</p>
      </div>

      {/* Tab strip */}
      <div className="border-b">
        <nav className="-mb-px flex gap-6" aria-label="Settings tabs">
          {TABS.map((tab) => {
            const isActive = tab.id === activeTab
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`whitespace-nowrap border-b-2 px-1 py-3 text-sm font-medium transition-colors ${
                  isActive
                    ? 'border-primary text-foreground'
                    : 'border-transparent text-muted-foreground hover:border-border hover:text-foreground'
                }`}
                aria-current={isActive ? 'page' : undefined}
              >
                {tab.label}
              </button>
            )
          })}
        </nav>
      </div>

      {/* Active panel */}
      <div>{active.panel}</div>
    </div>
  )
}
