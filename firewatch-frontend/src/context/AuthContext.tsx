/**
 * AuthContext -- global authentication state.
 *
 * Provides:
 *   user        -- the currently logged-in User, or null if not authenticated
 *   isLoading   -- true while the initial /api/auth/me check is in flight
 *   login()     -- calls the login API, updates user state
 *   logout()    -- calls the logout API, clears user state
 *
 * How it works:
 *   On mount, it calls GET /api/auth/me. If the HTTP-only access token cookie
 *   is present and valid, the backend returns the user and we hydrate state.
 *   If it returns 401, the user is not authenticated (user stays null).
 *
 *   This means on page refresh, authentication state is restored automatically
 *   without needing to store anything in localStorage.
 */

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { authApi, ApiError } from '@/services/api'
import type { User } from '@/types'

interface AuthContextValue {
  user: User | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  loginWithSSO: () => void
  ssoAvailable: boolean
  ssoProviderName: string | null
  refreshUser: () => Promise<void>
}

function loginWithSSO(): void {
  globalThis.location.href = '/api/auth/sso/login'
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { readonly children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [ssoAvailable, setSsoAvailable] = useState(false)
  const [ssoProviderName, setSsoProviderName] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      authApi.me().then((data) => setUser(data as User)).catch((err) => {
        if (!(err instanceof ApiError && err.status === 401)) {
          console.error('Auth check failed:', err)
        }
        setUser(null)
      }),
      authApi.getSsoConfig().then(({ enabled, provider_name }) => {
        setSsoAvailable(enabled)
        setSsoProviderName(provider_name)
      }).catch(() => { /* SSO config unavailable — silently disable */ }),
    ]).finally(() => setIsLoading(false))
  }, [])

  async function login(email: string, password: string): Promise<void> {
    const data = await authApi.login(email, password)
    setUser({
      id: data.user_id,
      email: data.email,
      full_name: data.full_name,
      role: data.role as User['role'],
      is_active: data.is_active,
      created_at: data.created_at,
      has_password: data.has_password,
      must_change_password: data.must_change_password,
    })
  }

  async function logout(): Promise<void> {
    await authApi.logout()
    setUser(null)
  }

  async function refreshUser(): Promise<void> {
    await authApi.me().then((data) => setUser(data as User)).catch((err) => {
      if (!(err instanceof ApiError && err.status === 401)) {
        console.error('Auth refresh failed:', err)
      }
      setUser(null)
    })
  }

  const value = useMemo(
    () => ({ user, isLoading, login, logout, loginWithSSO, ssoAvailable, ssoProviderName, refreshUser }),
    [user, isLoading, ssoAvailable, ssoProviderName],
  )

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

/**
 * useAuth() -- access auth state from any component.
 *
 * Must be used inside <AuthProvider>. Throws if called outside.
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>')
  return ctx
}
