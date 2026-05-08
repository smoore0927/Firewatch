import { useEffect, useRef, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { Download } from 'lucide-react'
import { dashboardApi, ApiError } from '@/services/api'
import type { DashboardSummary, ScoreTotalsBySeverityResponse, Severity } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import ExportReportDialog from '@/components/dashboard/ExportReportDialog'

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
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const today = new Date()
  const ninetyDaysAgo = new Date(today)
  ninetyDaysAgo.setDate(today.getDate() - 90)

  const [startDate, setStartDate] = useState(toDateStr(ninetyDaysAgo))
  const [endDate, setEndDate] = useState(toDateStr(today))
  const [totals, setTotals] = useState<ScoreTotalsBySeverityResponse | null>(null)
  const [visible, setVisible] = useState<Record<Severity, boolean>>({
    low: false,
    medium: true,
    high: true,
    critical: true,
  })
  const [exportOpen, setExportOpen] = useState(false)

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

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight mb-1">Dashboard</h1>
          <p className="text-muted-foreground text-sm">Risk register overview</p>
        </div>
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

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {!isLoading && summary && (
        <div className="space-y-4">
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
                <CardTitle className="text-sm font-medium">Overdue Treatments</CardTitle>
              </CardHeader>
              <CardContent>
                <p className={cn('text-3xl font-bold', summary.overdue_treatments > 0 && 'text-red-600')}>
                  {summary.overdue_treatments}
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

          <div>
            <h2 className="text-sm font-medium mb-3">Risk Matrix</h2>
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
          </div>

          <Card ref={chartRef}>
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
                  <div className="flex items-center gap-2">
                    <Label htmlFor="start-date" className="text-xs whitespace-nowrap">From</Label>
                    <Input
                      id="start-date"
                      type="date"
                      value={startDate}
                      max={endDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className="h-8 text-xs w-36"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Label htmlFor="end-date" className="text-xs whitespace-nowrap">To</Label>
                    <Input
                      id="end-date"
                      type="date"
                      value={endDate}
                      min={startDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="h-8 text-xs w-36"
                    />
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {totals && totals.points.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
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
                        dot={{ r: 3 }}
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
