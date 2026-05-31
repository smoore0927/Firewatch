import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { AlertTriangle, ChevronRight, Download, X } from 'lucide-react'
import { dashboardApi, risksApi, ApiError } from '@/services/api'
import { currentScore, scoreLabel } from '@/types'
import type { ActionQueueResponse, DashboardSummary, Risk, ScoreTotalsBySeverityResponse, Severity } from '@/types'
import { Badge, scoreToBadgeVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { useAuth } from '@/context/AuthContext'
import ExportReportDialog from '@/components/dashboard/ExportReportDialog'
import { DateRangePicker, type RangePreset } from '@/components/DateRangePicker'

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
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function cellColor(score: number): string {
  if (score > 20) return 'bg-red-500 text-white'
  if (score > 12) return 'bg-orange-400 text-white'
  if (score > 5)  return 'bg-yellow-400 text-gray-900'
  return 'bg-green-500 text-white'
}

function effectiveLI(risk: Risk): { likelihood: number; impact: number } | null {
  const a = risk.assessments[0]
  if (!a) return null
  if (a.residual_likelihood != null && a.residual_impact != null) {
    return { likelihood: a.residual_likelihood, impact: a.residual_impact }
  }
  return { likelihood: a.likelihood, impact: a.impact }
}

export default function DashboardPage() {
  const { user } = useAuth()
  const scopeLabel = user?.role === 'risk_owner' ? 'Showing your risks' : 'Showing all risks'

  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [risks, setRisks] = useState<Risk[]>([])
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
  const [selectedCell, setSelectedCell] = useState<{ likelihood: number; impact: number } | null>(null)
  const [drillPage, setDrillPage] = useState(1)
  const [drillPageSize, setDrillPageSize] = useState(5)
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
    dashboardApi.getActionQueue(1).then(setActionQueue).catch(() => {})
  }, [])

  useEffect(() => {
    risksApi.list().then((data) => setRisks(data.items)).catch(() => {})
  }, [])

  const matrixCounts = useMemo(() => {
    const grid: number[][] = Array.from({ length: 5 }, () => Array<number>(5).fill(0))
    for (const r of risks) {
      if (r.status !== 'open' && r.status !== 'in_progress') continue
      const li = effectiveLI(r)
      if (!li) continue
      if (li.likelihood < 1 || li.likelihood > 5 || li.impact < 1 || li.impact > 5) continue
      grid[li.likelihood - 1][li.impact - 1] += 1
    }
    return grid
  }, [risks])

  const selectedRisks = useMemo(() => {
    if (!selectedCell) return []
    return risks.filter((r) => {
      if (r.status !== 'open' && r.status !== 'in_progress') return false
      const li = effectiveLI(r)
      if (!li) return false
      return li.likelihood === selectedCell.likelihood && li.impact === selectedCell.impact
    })
  }, [risks, selectedCell])

  const pagedSelectedRisks = useMemo(() => {
    const start = (drillPage - 1) * drillPageSize
    return selectedRisks.slice(start, start + drillPageSize)
  }, [selectedRisks, drillPage, drillPageSize])

  useEffect(() => { setDrillPage(1) }, [selectedCell])

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
          <Card className={cn(hasOverdue && 'border-l-4 border-l-destructive bg-destructive/15 dark:bg-destructive/25')}>
            <div className="flex items-center gap-3 px-5 py-3">
              {hasOverdue && <AlertTriangle className="h-4 w-4 text-destructive shrink-0" />}
              <span className="text-sm font-medium">Overdue Items</span>
              <span className="text-sm text-muted-foreground">·</span>
              {actionQueue === null && (
                <span className="text-sm text-muted-foreground">Loading…</span>
              )}
              {actionQueue !== null && actionQueue.total === 0 && (
                <span className="text-sm text-muted-foreground">You're all caught up.</span>
              )}
              {actionQueue !== null && actionQueue.total > 0 && (
                <Link
                  to="/action-queue"
                  className="text-sm text-primary hover:underline inline-flex items-center gap-1"
                >
                  View {actionQueue.total} overdue {actionQueue.total === 1 ? 'item' : 'items'}
                  <ChevronRight className="h-3.5 w-3.5" />
                </Link>
              )}
            </div>
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
                <p className="text-3xl font-bold">{summary.by_status.open ?? 0}</p>
                <CardDescription>Awaiting action</CardDescription>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">In Progress</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{summary.by_status.in_progress ?? 0}</p>
                <CardDescription>Being addressed</CardDescription>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Overdue Responses</CardTitle>
              </CardHeader>
              <CardContent>
                <p className={cn('text-3xl font-bold', summary.overdue_responses > 0 && 'text-red-600 dark:text-red-400')}>
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
                <p className={cn('text-3xl font-bold', summary.overdue_reviews > 0 && 'text-red-600 dark:text-red-400')}>
                  {summary.overdue_reviews}
                </p>
                <CardDescription>Past review date</CardDescription>
              </CardContent>
            </Card>
          </div>

          <div className="flex flex-col lg:flex-row gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Risk heatmap</CardTitle>
                <CardDescription>
                  Open and in-progress risks by likelihood × impact. Click a cell to see the risks. Uses residual score when available.
                </CardDescription>
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
                          const count = matrixCounts[likelihood - 1]?.[impact - 1] ?? 0
                          const score = likelihood * impact
                          const isSelected =
                            selectedCell?.likelihood === likelihood && selectedCell?.impact === impact
                          const baseClass = cn(
                            'w-11 h-11 flex items-center justify-center rounded-lg text-sm font-bold',
                            cellColor(score),
                            isSelected && 'ring-2 ring-primary ring-offset-2',
                          )
                          if (count === 0) {
                            return (
                              <div
                                key={impact}
                                className={cn(baseClass, 'cursor-default')}
                                aria-label={`No risks at likelihood ${likelihood}, impact ${impact}`}
                              >
                                {''}
                              </div>
                            )
                          }
                          return (
                            <button
                              key={impact}
                              type="button"
                              aria-pressed={isSelected}
                              aria-label={`${count} risks at likelihood ${likelihood}, impact ${impact}`}
                              onClick={() =>
                                setSelectedCell((prev) =>
                                  prev?.likelihood === likelihood && prev?.impact === impact
                                    ? null
                                    : { likelihood, impact },
                                )
                              }
                              className={cn(baseClass, 'cursor-pointer hover:opacity-90')}
                            >
                              {count}
                            </button>
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

          {selectedCell && (
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <CardTitle className="text-sm font-medium">
                      Risks at likelihood {selectedCell.likelihood}, impact {selectedCell.impact}
                    </CardTitle>
                    <CardDescription>
                      Open and in-progress risks bucketed using residual score when available.
                    </CardDescription>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedCell(null)}
                    aria-label="Clear selected cell"
                    className="text-muted-foreground hover:text-foreground p-1 -m-1"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </CardHeader>
              <CardContent>
                {selectedRisks.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No matching risks.</p>
                ) : (
                  <>
                    <ul className="divide-y divide-border">
                      {pagedSelectedRisks.map((risk) => {
                        const score = currentScore(risk)
                        return (
                          <li key={risk.id} className="flex items-center gap-3 py-2">
                            <span className="font-mono text-xs text-muted-foreground w-20 shrink-0">
                              {risk.risk_id}
                            </span>
                            <Link
                              to={`/risks/${risk.risk_id}`}
                              className="flex-1 min-w-0 truncate text-sm font-medium hover:underline"
                            >
                              {risk.title}
                            </Link>
                            {score !== null ? (
                              <Badge variant={scoreToBadgeVariant(score)}>
                                {score} — {scoreLabel(score)}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground italic text-xs">Unscored</span>
                            )}
                            <Badge variant={risk.status}>
                              {risk.status.replace('_', ' ')}
                            </Badge>
                          </li>
                        )
                      })}
                    </ul>
                    {(() => {
                      const totalPages = Math.max(1, Math.ceil(selectedRisks.length / drillPageSize))
                      return (
                        <div className="mt-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
                          <div className="flex items-center gap-2">
                            <label htmlFor="drill-page-size">Per page</label>
                            <select
                              id="drill-page-size"
                              value={drillPageSize}
                              onChange={(e) => { setDrillPageSize(Number(e.target.value)); setDrillPage(1) }}
                              className="rounded-md border border-input bg-background px-2 py-1 text-xs"
                            >
                              {[5, 10, 25, 50, 100].map((n) => (
                                <option key={n} value={n}>{n}</option>
                              ))}
                            </select>
                            <span>· {selectedRisks.length} total</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button size="sm" variant="outline" disabled={drillPage <= 1} onClick={() => setDrillPage((p) => p - 1)}>
                              Previous
                            </Button>
                            <span>Page {drillPage} of {totalPages}</span>
                            <Button size="sm" variant="outline" disabled={drillPage >= totalPages} onClick={() => setDrillPage((p) => p + 1)}>
                              Next
                            </Button>
                          </div>
                        </div>
                      )
                    })()}
                  </>
                )}
              </CardContent>
            </Card>
          )}
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
