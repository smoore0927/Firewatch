import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, AlertTriangle } from 'lucide-react'
import { dashboardApi, ApiError } from '@/services/api'
import type { ActionQueueResponse } from '@/types'
import ActionQueueRow from '@/components/dashboard/ActionQueueRow'

export default function ActionQueuePage() {
  const [data, setData] = useState<ActionQueueResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    dashboardApi.getActionQueue(200)
      .then(setData)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          setError('Your session has expired. Please sign in again.')
        } else {
          setError('Could not load action queue.')
        }
      })
  }, [])

  let subtitle: string
  if (data === null) {
    subtitle = 'Loading…'
  } else if (data.items.length === 0) {
    subtitle = "You're all caught up — no overdue items."
  } else {
    subtitle = `${data.total} overdue ${data.total === 1 ? 'item' : 'items'} to address`
  }

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/dashboard"
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
        >
          <ArrowLeft className="h-4 w-4" /> Dashboard
        </Link>
        <h1 className="text-2xl font-bold tracking-tight mb-1 flex items-center gap-2">
          {data && data.items.length > 0 && (
            <AlertTriangle className="h-5 w-5 text-destructive" />
          )}
          Action Queue
        </h1>
        <p className="text-muted-foreground text-sm">{subtitle}</p>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {data && data.items.length > 0 && (
        <div className="rounded-lg border overflow-hidden">
          <ul className="divide-y divide-border">
            {data.items.map((item) => (
              <li key={`${item.kind}-${item.risk_id}-${item.due_date}`}>
                <ActionQueueRow item={item} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
