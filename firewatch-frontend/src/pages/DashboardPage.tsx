import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { AlertTriangle, ChevronDown, ChevronRight, ChevronUp, Download } from 'lucide-react'
import { dashboardApi, ApiError } from '@/services/api'
import type { ActionQueueResponse, DashboardSummary, ScoreTotalsBySeverityResponse, Severity } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { useAuth } from '@/context/AuthContext'
import ActionQueueRow from '@/components/dashboard/ActionQueueRow'
import ExportReportDialog from '@/components/dashboard/ExportReportDialog'
import { DateRangePicker, type RangePreset } from '@/components/DateRangePicker'

const DASHBOARD_ACTION_LIMIT = 3

const SEVERITY_COLORS: Record<Severity, string> = {
  low: '#22c55e',
  medium: '#facc15',
  high: '#f97316',
  critical: '#ef4444',
}

const SEVERITY_LABELS: Record<Severity, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
}

const SEVERITY_KEYS: Severity[] = ['low', 'medium', 'high', 'critical']

function toDateStr(d: Date): string {
  return d.toISOString().split('T')[0]
}

function cellColor(score: number): string {
  if (score > 20) return 'bg-red-500 text-white'
  if (score > 12) return 'bg-orange-400 text-white'
  if (score > 5)  return 'bg-yellow-400 text-gray-900'
  return 'bg-green-500 text-white'
}

export default function DashboardPage() {
  const { user } = useAuth()
  const scopeLabel = user?.role === 'risk_owner' ? 'Showing your risks' : 'Showing all risks'

  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [actionQueue, setActionQueue] = useState<ActionQueueResponse | null>(null)
  const hasOverdue = (actionQueue?.items.length ?? 0) > 0
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const today = new Date()
  const ninetyDaysAgo = new Date(today)
  ninetyDaysAgo.setDate(today.getDate() - 90)

  const [startDate, setStartDate] = useState(toDateStr(ninetyDaysAgo))
  const [endDate, setEndDate] = useState(toDateStr(today))
  const [range, setRange] = useState<RangePreset>('90d')
  const [totals, setTotals] = useState<ScoreTotalsBySeverityResponse | null>(null)
  const [visible, setVisible] = useState<Record<Severity, boolean>>({
    low: false,
    medium: true,
    high: true,
    critical: true,
  })
  const [exportOpen, setExportOpen] = useState(false)
  const [actionQueueCollapsed, setActionQueueCollapsed] = useState<boolean>(() => {
    return localStorage.getItem('dashboard.actionQueue.collapsed') === '1'
  })

  function toggleActionQueueCollapsed() {
    setActionQueueCollapsed((prev) => {
      const next = !prev
      localStorage.setItem('dashboard.actionQueue.collapsed', next ? '1' : '0')
      return next
    })
  }

  const matrixRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    dashboardApi.getSummary()
      .then(setSummary)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          setError('Your session has expired. Please sign in again.')
        } else {
          setError('Could not load dashboard. Check that the backend is running and try refreshing.')
        }
      })
      .finally(() => setIsLoading(false))
  }, [])

  useEffect(() => {
    dashboardApi.getScoreTotalsBySeverity(startDate, endDate)
      .then(setTotals)
      .catch(() => {})
  }, [startDate, endDate])

  useEffect(() => {
    dashboardApi.getActionQueue(DASHBOARD_ACTION_LIMIT).then(setActionQueue).catch(() => {})
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight mb-1">Dashboard</h1>
          <p className="text-muted-foreground text-sm">Risk register overview</p>
          <p className="text-sm text-muted-foreground">{scopeLabel}</p>
        </div>
        <div className="flex items-center gap-2">
          <DateRangePicker
            start={startDate}
            end={endDate}
            preset={range}
            onChange={({ start, end, preset }) => {
              setStartDate(start)
              setEndDate(end)
              setRange(preset)
            }}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => setExportOpen(true)}
            disabled={!summary}
          >
            <Download className="h-4 w-4" />
            Export PDF
          </Button>
        </div>
      </div>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {!isLoading && summary && (
        <div className="space-y-4">
          <Card className={cn(hasOverdue && 'border-l-4 border-l-destructive bg-destructive/5')}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    {hasOverdue && <AlertTriangle className="h-4 w-4 text-destructive" />}
                    Action Queue
                  </CardTitle>
                  <CardDescription>Overdue items to address</CardDescription>
                </div>
                <button
                  type="button"
                  onClick={toggleActionQueueCollapsed}
                  aria-label={actionQueueCollapsed ? 'Expand Action Queue' : 'Collapse Action Queue'}
                  aria-expanded={!actionQueueCollapsed}
                  className="text-muted-foreground hover:text-foreground p-1 -m-1"
                >
                  {actionQueueCollapsed
                    ? <ChevronDown className="h-4 w-4" />
                    : <ChevronUp className="h-4 w-4" />}
                </button>
              </div>
            </CardHeader>
            {!actionQueueCollapsed && (
              <CardContent>
                {actionQueue === null && (
                  <p className="text-sm text-muted-foreground">Loading…</p>
                )}
                {actionQueue !== null && actionQueue.items.length === 0 && (
                  <p className="text-sm text-muted-foreground">You're all caught up — no overdue items.</p>
                )}
                {actionQueue !== null && actionQueue.items.length > 0 && (
                  <>
                    <ul className="divide-y divide-border">
                      {actionQueue.items.map((item) => (
                        <li key={`${item.kind}-${item.risk_id}-${item.due_date}`}>
                          <ActionQueueRow item={item} />
                        </li>
                      ))}
                    </ul>
                    {actionQueue.total > actionQueue.items.length && (
                      <div className="pt-3 mt-2 border-t border-border">
                        <Link
                          to="/action-queue"
                          className="text-xs text-primary hover:underline inline-flex items-center gap-1"
                        >
                          View all {actionQueue.total} overdue items
                          <ChevronRight className="h-3 w-3" />
                        </Link>
                      </div>
                    )}
                  </>
                )}
              </CardContent>
            )}
          </Card>

          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Total Risks</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{summary.total}</p>
                <CardDescription>Active risks</CardDescription>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Open</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{summary.by_status['open'] ?? 0}</p>
                <CardDescription>Awaiting action</CardDescription>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">In Progress</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{summary.by_status['in_progress'] ?? 0}</p>
                <CardDescription>Being addressed</CardDescription>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Overdue Responses</CardTitle>
              </CardHeader>
              <CardContent>
                <p className={cn('text-3xl font-bold', summary.overdue_responses > 0 && 'text-red-600')}>
                  {summary.overdue_responses}
                </p>
                <CardDescription>Past target date</CardDescription>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Overdue Reviews</CardTitle>
              </CardHeader>
              <CardContent>
                <p className={cn('text-3xl font-bold', summary.overdue_reviews > 0 && 'text-red-600')}>
                  {summary.overdue_reviews}
                </p>
                <CardDescription>Past review date</CardDescription>
              </CardContent>
            </Card>
          </div>

          <div className="flex flex-col lg:flex-row gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Risk Matrix</CardTitle>
              </CardHeader>
              <CardContent>
                <div ref={matrixRef} className="flex gap-3 items-start bg-background p-2">
                  {/* Y-axis label */}
                  <div className="flex items-center justify-center self-stretch">
                    <span
                      className="text-xs text-muted-foreground"
                      style={{ writingMode: 'vertical-lr', transform: 'rotate(180deg)' }}
                    >
                      Likelihood
                    </span>
                  </div>

                  <div className="flex flex-col gap-1">
                    {/* Rows: likelihood 5 → 1 (high at top) */}
                    {[5, 4, 3, 2, 1].map((likelihood) => (
                      <div key={likelihood} className="flex items-center gap-1">
                        <span className="text-xs text-muted-foreground w-4 text-right">{likelihood}</span>
                        {[1, 2, 3, 4, 5].map((impact) => {
                          const count = summary.risk_matrix[likelihood - 1]?.[impact - 1] ?? 0
                          const score = likelihood * impact
                          return (
                            <div
                              key={impact}
                              className={cn(
                                'w-11 h-11 flex items-center justify-center rounded-lg text-sm font-bold',
                                cellColor(score),
                              )}
                            >
                              {count > 0 ? count : ''}
                            </div>
                          )
                        })}
                      </div>
                    ))}

                    {/* X-axis: impact labels */}
                    <div className="flex items-center gap-1 mt-1">
                      <div className="w-4" />
                      {[1, 2, 3, 4, 5].map((i) => (
                        <div key={i} className="w-11 text-center text-xs text-muted-foreground">{i}</div>
                      ))}
                    </div>
                    <div className="text-center text-xs text-muted-foreground ml-5">Impact</div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card ref={chartRef} className="flex-1 min-w-0 flex flex-col">
            <CardHeader className="pb-2">
              <div className="flex items-end justify-between gap-4 flex-wrap">
                <CardTitle className="text-sm font-medium">Risk Score Totals by Severity</CardTitle>
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="flex items-center gap-3">
                    {SEVERITY_KEYS.map((key) => (
                      <div key={key} className="flex items-center gap-1.5">
                        <input
                          id={`sev-${key}`}
                          type="checkbox"
                          checked={visible[key]}
                          onChange={(e) =>
                            setVisible((prev) => ({ ...prev, [key]: e.target.checked }))
                          }
                          className="h-4 w-4 rounded border-input accent-primary"
                        />
                        <Label htmlFor={`sev-${key}`} className="flex items-center gap-1.5 text-xs cursor-pointer">
                          <span
                            className="inline-block h-2.5 w-2.5 rounded-full"
                            style={{ backgroundColor: SEVERITY_COLORS[key] }}
                          />
                          {SEVERITY_LABELS[key]}
                        </Label>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent className="flex-1 min-h-0">
              {totals && totals.points.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={totals.points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip
                      formatter={(value: number, name: string) => [value, name]}
                    />
                    <Legend />
                    {SEVERITY_KEYS.filter((k) => visible[k]).map((key) => (
                      <Line
                        key={key}
                        type="monotone"
                        dataKey={key}
                        name={SEVERITY_LABELS[key]}
                        stroke={SEVERITY_COLORS[key]}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 5 }}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-12">
                  No assessments recorded in this date range.
                </p>
              )}
            </CardContent>
          </Card>
          </div>
        </div>
      )}

      <ExportReportDialog
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        defaultStart={startDate}
        defaultEnd={endDate}
        matrixEl={matrixRef.current}
        chartEl={chartRef.current}
        onError={(msg) => setError(msg)}
      />
    </div>
  )
}
