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
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
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
import { ShieldAlert } from 'lucide-react'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

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
                  onChange={(e) => setEmail(e.target.value)}
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
                  onChange={(e) => setPassword(e.target.value)}
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
          </CardContent>
        </Card>

      </div>
    </div>
  )
}
