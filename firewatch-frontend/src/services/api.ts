/**
 * Centralised API client.
 *
 * All fetch calls go through here so that:
 *   - credentials: 'include' is set everywhere (sends the HTTP-only cookie)
 *   - 401 responses trigger a token refresh attempt before failing
 *   - JSON parsing and error handling are consistent
 *
 * The base URL is empty in development because Vite's proxy forwards
 * /api/... requests to the backend on port 8000. In production, set
 * VITE_API_BASE_URL in your environment.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

let isRefreshing = false

async function refreshToken(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/api/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
    return res.ok
  } catch {
    return false
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    credentials: 'include',   // always send cookies
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  // If 401 and we haven't already tried refreshing, attempt a token refresh
  // and retry the original request once.
  if (res.status === 401 && !isRefreshing) {
    isRefreshing = true
    const refreshed = await refreshToken()
    isRefreshing = false

    if (refreshed) {
      return request<T>(path, options)  // retry with new access token
    }
    // Refresh failed -- throw so ProtectedRoute redirects to /login.
    // Never use window.location.href here: if the caller is already on /login
    // (e.g. the initial /me check on page load) that causes an infinite reload loop.
    throw new ApiError(401, 'Session expired')
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch { /* response had no JSON body */ }
    throw new ApiError(res.status, detail)
  }

  // 204 No Content -- return empty object cast to T
  if (res.status === 204) return {} as T

  return res.json() as Promise<T>
}

// -------------------------------------------------------------------------
// Auth
// -------------------------------------------------------------------------

export const authApi = {
  login: (email: string, password: string) =>
    request<{ user_id: number; email: string; role: string; full_name: string | null; is_active: boolean; created_at: string }>(
      '/api/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) }
    ),

  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),

  me: () =>
    request<{ id: number; email: string; role: string; full_name: string | null; is_active: boolean; created_at: string }>(
      '/api/auth/me'
    ),
}

// -------------------------------------------------------------------------
// Risks
// -------------------------------------------------------------------------

import type { DashboardSummary, Risk, RiskAssessment, RiskCreate, RiskListResponse, RiskUpdate, ScoreHistoryResponse, User } from '@/types'

export const risksApi = {
  list: (params?: { status?: string; category?: string; owner_id?: number; due_for_review?: boolean; skip?: number; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set('status', params.status)
    if (params?.category) qs.set('category', params.category)
    if (params?.owner_id) qs.set('owner_id', String(params.owner_id))
    if (params?.due_for_review) qs.set('due_for_review', 'true')
    if (params?.skip !== undefined) qs.set('skip', String(params.skip))
    if (params?.limit !== undefined) qs.set('limit', String(params.limit))
    const query = qs.toString() ? `?${qs.toString()}` : ''
    return request<RiskListResponse>(`/api/risks${query}`)
  },

  get: (riskId: string) => request<Risk>(`/api/risks/${riskId}`),

  create: (data: RiskCreate) =>
    request<Risk>('/api/risks', { method: 'POST', body: JSON.stringify(data) }),

  update: (riskId: string, data: RiskUpdate) =>
    request<Risk>(`/api/risks/${riskId}`, { method: 'PUT', body: JSON.stringify(data) }),

  delete: (riskId: string) =>
    request<void>(`/api/risks/${riskId}`, { method: 'DELETE' }),

  // Adds a new assessment row to an existing risk.
  // Returns the updated full Risk so the detail page can refresh in one call.
  addAssessment: (
    riskId: string,
    data: { likelihood: number; impact: number; notes?: string },
  ) =>
    request<Risk>(
      `/api/risks/${riskId}/assessments`,
      { method: 'POST', body: JSON.stringify(data) },
    ),
}

// -------------------------------------------------------------------------
// Users
// -------------------------------------------------------------------------

export const usersApi = {
  // Returns active users who can be assigned as risk owners (excludes executive_viewers).
  // Requires admin or security_analyst role — will 403 for other roles.
  listAssignable: () => request<User[]>('/api/users/assignable'),
}

// -------------------------------------------------------------------------
// Dashboard
// -------------------------------------------------------------------------

export const dashboardApi = {
  getSummary: () => request<DashboardSummary>('/api/dashboard/summary'),

  getScoreHistory: (start: string, end: string) =>
    request<ScoreHistoryResponse>(`/api/dashboard/score-history?start=${start}&end=${end}`),
}

export { ApiError }
