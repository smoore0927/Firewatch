/**
 * Login page — the only public route in the app.
 *
 * Security notes:
 *   - Error message is intentionally generic ("Invalid email or password") so
 *     an attacker cannot enumerate which emails exist in the system.
 *   - autoComplete attributes are set so password managers work correctly.
 *   - The form uses noValidate so we control the UX, but the <Input type="email">
 *     and required attributes are still present for accessibility and are
 *     enforced server-side regardless.
 *   - After a successful login the backend sets HTTP-only cookies. We never
 *     touch or store the token in JS -- the browser handles it automatically.
 */
import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { authApi } from '@/services/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { ShieldAlert, LogIn } from 'lucide-react'

const SSO_ERROR_MESSAGES: Record<string, string> = {
  not_configured: 'SSO is not configured. Contact your administrator.',
  discovery_failed: 'Could not reach the SSO provider. Try again or contact your administrator.',
  discovery_invalid: 'SSO provider returned an invalid configuration. Contact your administrator.',
  invalid_state: 'Your SSO session expired. Please try again.',
  state_mismatch: 'SSO sign-in could not be verified. Please try again.',
  missing_code: 'The SSO provider did not return an authorization code.',
  token_exchange_failed: 'Could not complete SSO sign-in. Please try again.',
  no_id_token: 'The SSO provider did not return an identity token.',
  invalid_id_token: 'The SSO provider returned an invalid identity token. Contact your administrator.',
  no_email: 'Your SSO account does not have an email address. Contact your administrator.',
  email_not_verified: "Your SSO account's email address has not been verified. Contact your administrator.",
  account_disabled: 'Your account is disabled. Contact your administrator.',
}

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [ssoConfig, setSsoConfig] = useState<{ enabled: boolean; provider_name: string | null } | null>(null)

  const ssoErrorCode = searchParams.get('sso_error')
  const ssoErrorMessage = ssoErrorCode
    ? (SSO_ERROR_MESSAGES[ssoErrorCode] ?? 'SSO sign-in failed. Please try again or use your email and password.')
    : null

  useEffect(() => {
    authApi.getSsoConfig().then(setSsoConfig).catch(() => {})
  }, [])

  function handleInputChange(setter: (v: string) => void) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setter(e.target.value)
      setError('')
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      await login(email, password)
      // Replace so the login page isn't in history -- pressing Back
      // after login won't take the user back to the login screen.
      navigate('/dashboard', { replace: true })
    } catch {
      // Generic message regardless of whether the email or password was wrong.
      setError('Invalid email or password.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">

        {/* Brand mark */}
        <div className="flex items-center justify-center gap-2">
          <ShieldAlert className="h-8 w-8 text-primary" />
          <span className="text-2xl font-bold tracking-tight">Firewatch</span>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Sign in</CardTitle>
            <CardDescription>
              Enter your credentials to access the risk register.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {ssoErrorMessage && (
              <p role="alert" className="text-sm text-destructive mb-4">
                {ssoErrorMessage}
              </p>
            )}

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>

              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  placeholder="you@example.com"
                  value={email}
                  onChange={handleInputChange(setEmail)}
                  disabled={isSubmitting}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={handleInputChange(setPassword)}
                  disabled={isSubmitting}
                />
              </div>

              {/* role="alert" means screen readers announce this immediately */}
              {error && (
                <p role="alert" className="text-sm text-destructive">
                  {error}
                </p>
              )}

              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting ? 'Signing in...' : 'Sign in'}
              </Button>

            </form>

            {ssoConfig?.enabled === true && (
              <>
                <div className="flex items-center gap-3 text-xs text-muted-foreground mt-4">
                  <div className="flex-1 h-px bg-border" />
                  <span>or</span>
                  <div className="flex-1 h-px bg-border" />
                </div>

                <a
                  href="/api/auth/sso/login"
                  className="inline-flex items-center justify-center gap-2 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow-sm hover:bg-accent hover:text-accent-foreground transition-colors w-full mt-4"
                >
                  <LogIn className="h-4 w-4" />
                  Sign in with {ssoConfig.provider_name}
                </a>
              </>
            )}
          </CardContent>
        </Card>

      </div>
    </div>
  )
}
