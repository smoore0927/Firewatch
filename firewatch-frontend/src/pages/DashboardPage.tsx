import { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { dashboardApi, ApiError } from '@/services/api'
import type { DashboardSummary, ScoreHistoryResponse } from '@/types'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

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
  const [history, setHistory] = useState<ScoreHistoryResponse | null>(null)

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
    dashboardApi.getScoreHistory(startDate, endDate)
      .then(setHistory)
      .catch(() => {})
  }, [startDate, endDate])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight mb-1">Dashboard</h1>
        <p className="text-muted-foreground text-sm">Risk register overview</p>
      </div>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {!isLoading && summary && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
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
          </div>

          <div>
            <h2 className="text-sm font-medium mb-3">Risk Matrix</h2>
            <div className="flex gap-3 items-start">
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

          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-end justify-between gap-4 flex-wrap">
                <CardTitle className="text-sm font-medium">Average Risk Score Over Time</CardTitle>
                <div className="flex items-center gap-4">
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
              {history && history.points.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={history.points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis domain={[0, 25]} tick={{ fontSize: 11 }} />
                    <Tooltip
                      formatter={(value: number, name: string) =>
                        name === 'avg_score' ? [value.toFixed(1), 'Avg Score'] : [value, 'Assessments']
                      }
                    />
                    {/* Severity band boundaries */}
                    <ReferenceLine y={5}  stroke="#22c55e" strokeDasharray="4 4" label={{ value: 'Low', fontSize: 10, fill: '#22c55e' }} />
                    <ReferenceLine y={12} stroke="#facc15" strokeDasharray="4 4" label={{ value: 'Medium', fontSize: 10, fill: '#ca8a04' }} />
                    <ReferenceLine y={20} stroke="#f97316" strokeDasharray="4 4" label={{ value: 'High', fontSize: 10, fill: '#f97316' }} />
                    <Line type="monotone" dataKey="avg_score" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 6 }} />
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
    </div>
  )
}
