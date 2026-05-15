import { useEffect, useMemo, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { analyticsApi, ApiError } from '@/services/api'
import type {
  ResidualReductionResponse,
  Severity,
  VelocityMTTMResponse,
  VelocityThroughputResponse,
} from '@/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { CATEGORIES } from '@/lib/constants'

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

// Ordered high-to-low so the breakdown reads worst-first.
const SEVERITY_KEYS: Severity[] = ['critical', 'high', 'medium', 'low']

function toDateStr(d: Date): string {
  return d.toISOString().split('T')[0]
}

function fmt(value: number | null): string {
  return value === null ? '—' : String(value)
}

export default function AnalyticsPage() {
  const today = new Date()
  const ninetyDaysAgo = new Date(today)
  ninetyDaysAgo.setDate(today.getDate() - 90)

  const [startDate, setStartDate] = useState(toDateStr(ninetyDaysAgo))
  const [endDate, setEndDate] = useState(toDateStr(today))
  const [severity, setSeverity] = useState<Severity | ''>('')
  const [category, setCategory] = useState<string>('')

  const [mttm, setMttm] = useState<VelocityMTTMResponse | null>(null)
  const [throughput, setThroughput] = useState<VelocityThroughputResponse | null>(null)
  const [residual, setResidual] = useState<ResidualReductionResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const opts = useMemo(
    () => ({ severity: severity || undefined, category: category || undefined }),
    [severity, category],
  )

  useEffect(() => {
    analyticsApi.getResidualReduction(opts)
      .then(setResidual)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          setError('Your session has expired. Please sign in again.')
        } else {
          setError('Could not load analytics. Check that the backend is running and try refreshing.')
        }
      })
  }, [severity, category, opts])

  useEffect(() => {
    setIsLoading(true)
    Promise.all([
      analyticsApi.getMeanTimeToMitigation(startDate, endDate, opts),
      analyticsApi.getThroughput(startDate, endDate, opts),
    ])
      .then(([m, t]) => {
        setMttm(m)
        setThroughput(t)
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          setError('Your session has expired. Please sign in again.')
        } else {
          setError('Could not load analytics. Check that the backend is running and try refreshing.')
        }
      })
      .finally(() => setIsLoading(false))
  }, [startDate, endDate, severity, category, opts])

  const openedSum = throughput?.points.reduce((acc, p) => acc + p.opened, 0) ?? 0
  const closedSum = throughput?.points.reduce((acc, p) => acc + p.closed, 0) ?? 0

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight mb-1">Risk Velocity</h1>
          <p className="text-muted-foreground text-sm">
            Throughput, time-to-mitigation, and residual reduction over time.
          </p>
        </div>
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <Label htmlFor="severity-filter" className="text-xs whitespace-nowrap">Severity</Label>
            <select
              id="severity-filter"
              value={severity}
              onChange={(e) => setSeverity(e.target.value as Severity | '')}
              className="h-8 rounded-md border border-input bg-background px-2 text-xs shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">All severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <Label htmlFor="category-filter" className="text-xs whitespace-nowrap">Category</Label>
            <select
              id="category-filter"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="h-8 rounded-md border border-input bg-background px-2 text-xs shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">All categories</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
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

      {error && <p className="text-sm text-destructive">{error}</p>}

      {isLoading && !mttm && !throughput ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Mean time to mitigation</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">
                  {mttm?.mean_days === null || mttm === null ? '—' : `${mttm.mean_days} days`}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Median: {fmt(mttm?.median_days ?? null)} • {mttm?.count ?? 0} risks closed
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Residual reduction</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">
                  {residual?.avg_percentage === null || residual === null
                    ? '—'
                    : `${residual.avg_percentage}%`}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {fmt(residual?.avg_absolute ?? null)} avg score reduction • {residual?.count ?? 0} risks
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Throughput in window</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{openedSum}</p>
                <p className="text-xs text-muted-foreground mt-1">{openedSum} opened • {closedSum} closed</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Opened vs Closed by Month</CardTitle>
            </CardHeader>
            <CardContent>
              {throughput && throughput.points.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={throughput.points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="opened" name="Opened" fill="#3b82f6" />
                    <Bar dataKey="closed" name="Closed" fill="#10b981" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-12">
                  No activity in this date range.
                </p>
              )}
            </CardContent>
          </Card>

          {severity === '' && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">By Severity</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <h3 className="text-xs font-medium text-muted-foreground mb-3">
                      Mean time to mitigation
                    </h3>
                    <div className="space-y-2">
                      {SEVERITY_KEYS.map((key) => (
                        <div key={key} className="flex items-center justify-between text-sm">
                          <span className="flex items-center gap-2">
                            <span
                              className="inline-block h-2.5 w-2.5 rounded-full"
                              style={{ backgroundColor: SEVERITY_COLORS[key] }}
                            />
                            {SEVERITY_LABELS[key]}
                          </span>
                          <span className="font-medium">
                            {mttm?.by_severity[key] === null || mttm === null
                              ? '—'
                              : `${mttm.by_severity[key]} days`}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h3 className="text-xs font-medium text-muted-foreground mb-3">
                      Residual reduction
                    </h3>
                    <div className="space-y-2">
                      {SEVERITY_KEYS.map((key) => (
                        <div key={key} className="flex items-center justify-between text-sm">
                          <span className="flex items-center gap-2">
                            <span
                              className="inline-block h-2.5 w-2.5 rounded-full"
                              style={{ backgroundColor: SEVERITY_COLORS[key] }}
                            />
                            {SEVERITY_LABELS[key]}
                          </span>
                          <span className="font-medium">
                            {fmt(residual?.by_severity[key] ?? null)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
