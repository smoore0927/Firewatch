import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi, ApiError } from '@/services/api'
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
import { AlertTriangle, Info, KeyRound } from 'lucide-react'

const PASSWORD_POLICY_MESSAGE =
  'Password must be at least 12 characters and include an uppercase letter, a lowercase letter, a digit, and a special character.'

function isPasswordValid(password: string): boolean {
  if (password.length < 12) return false
  if (!/[A-Z]/.test(password)) return false
  if (!/[a-z]/.test(password)) return false
  if (!/\d/.test(password)) return false
  if (!/[^A-Za-z0-9]/.test(password)) return false
  return true
}

export default function SettingsPasswordPage() {
  const { user, refreshUser } = useAuth()
  const navigate = useNavigate()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const isSsoOnly = user?.has_password === false

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setSuccess(false)

    if (!isPasswordValid(newPassword)) {
      setError(PASSWORD_POLICY_MESSAGE)
      return
    }
    if (newPassword !== confirmPassword) {
      setError('New password and confirmation do not match.')
      return
    }

    const mustChange = user?.must_change_password ?? false
    setIsSubmitting(true)
    try {
      await authApi.changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      await refreshUser()
      if (mustChange) {
        navigate('/risks', { replace: true })
      } else {
        setSuccess(true)
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message ?? 'Something went wrong.')
      } else {
        setError('Something went wrong.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="max-w-md space-y-4">
      {user?.must_change_password && (
        <div className="flex items-start gap-3 rounded-md border border-amber-400 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-amber-500" />
          <p>
            <strong>Password change required.</strong> Your account was set up by an administrator.
            Please set a personal password before you can access Firewatch.
          </p>
        </div>
      )}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-muted-foreground" />
            <CardTitle className="text-base">Change password</CardTitle>
          </div>
          <CardDescription>
            Update the password used to sign in to your account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isSsoOnly ? (
            <div className="flex items-start gap-3 text-sm text-muted-foreground">
              <Info className="h-4 w-4 mt-0.5 shrink-0" />
              <p>
                Your account is provisioned via single sign-on. To change your password,
                please use your identity provider.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4" noValidate>

              <div className="space-y-2">
                <Label htmlFor="current-password">Current password</Label>
                <Input
                  id="current-password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={currentPassword}
                  onChange={(e) => { setCurrentPassword(e.target.value); setError(''); setSuccess(false) }}
                  disabled={isSubmitting}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="new-password">New password</Label>
                <Input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={newPassword}
                  onChange={(e) => { setNewPassword(e.target.value); setError(''); setSuccess(false) }}
                  disabled={isSubmitting}
                />
                <p className="text-xs text-muted-foreground">{PASSWORD_POLICY_MESSAGE}</p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm-password">Confirm new password</Label>
                <Input
                  id="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(e) => { setConfirmPassword(e.target.value); setError(''); setSuccess(false) }}
                  disabled={isSubmitting}
                />
              </div>

              {error && (
                <p role="alert" className="text-sm text-destructive">
                  {error}
                </p>
              )}

              {success && (
                <p role="status" className="text-sm text-green-600">
                  Password updated successfully.
                </p>
              )}

              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? 'Updating...' : 'Update password'}
              </Button>

            </form>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
