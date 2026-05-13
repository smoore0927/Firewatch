import { useCallback, useEffect, useState } from 'react'
import { Check, Plus, UserCheck, UserX, X } from 'lucide-react'
import { usersApi, ApiError } from '@/services/api'
import { useAuth } from '@/context/AuthContext'
import type { User, UserRole } from '@/types'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'admin', label: 'Admin' },
  { value: 'security_analyst', label: 'Security analyst' },
  { value: 'risk_owner', label: 'Risk owner' },
  { value: 'executive_viewer', label: 'Executive viewer' },
]

const ROLE_LABELS: Record<UserRole, string> = {
  admin: 'Admin',
  security_analyst: 'Security analyst',
  risk_owner: 'Risk owner',
  executive_viewer: 'Executive viewer',
}

function sortUsers(list: User[]): User[] {
  return [...list].sort((a, b) => a.email.localeCompare(b.email))
}

export default function SettingsUsersPage() {
  const { user: currentUser } = useAuth()
  const [users, setUsers] = useState<User[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [flashId, setFlashId] = useState<number | null>(null)
  const [pendingId, setPendingId] = useState<number | null>(null)
  const [showInactive, setShowInactive] = useState(false)
  const [isCreateOpen, setIsCreateOpen] = useState(false)

  const fetchUsers = useCallback((includeInactive: boolean) => {
    setIsLoading(true)
    setError(null)
    usersApi.list({ includeInactive })
      .then((data) => setUsers(sortUsers(data)))
      .catch((err) => {
        if (err instanceof ApiError) setError(err.message)
        else setError('Could not load users. Try again.')
      })
      .finally(() => setIsLoading(false))
  }, [])

  useEffect(() => { fetchUsers(showInactive) }, [fetchUsers, showInactive])

  async function handleRoleChange(target: User, newRole: UserRole) {
    if (newRole === target.role) return
    setError(null)
    setPendingId(target.id)
    const previous = users
    setUsers((prev) => prev.map((u) => (u.id === target.id ? { ...u, role: newRole } : u)))
    try {
      const updated = await usersApi.updateRole(target.id, newRole)
      setUsers((prev) => sortUsers(prev.map((u) => (u.id === updated.id ? updated : u))))
      setFlashId(target.id)
      globalThis.setTimeout(() => {
        setFlashId((current) => (current === target.id ? null : current))
      }, 2000)
    } catch (err) {
      setUsers(previous)
      if (err instanceof ApiError) setError(err.message)
      else setError('Could not update role. Try again.')
      fetchUsers(showInactive)
    } finally {
      setPendingId((current) => (current === target.id ? null : current))
    }
  }

  async function handleToggleActive(target: User) {
    setError(null)
    setPendingId(target.id)
    const previous = users
    const nextActive = !target.is_active
    setUsers((prev) => prev.map((u) => (u.id === target.id ? { ...u, is_active: nextActive } : u)))
    try {
      const updated = nextActive
        ? await usersApi.activate(target.id)
        : await usersApi.deactivate(target.id)
      setUsers((prev) => {
        const next = prev.map((u) => (u.id === updated.id ? updated : u))
        // When showInactive is off and a user was just deactivated, drop them from the view.
        const filtered = showInactive ? next : next.filter((u) => u.is_active)
        return sortUsers(filtered)
      })
      setFlashId(target.id)
      globalThis.setTimeout(() => {
        setFlashId((current) => (current === target.id ? null : current))
      }, 2000)
    } catch (err) {
      setUsers(previous)
      if (err instanceof ApiError) setError(err.message)
      else setError('Could not update status. Try again.')
      fetchUsers(showInactive)
    } finally {
      setPendingId((current) => (current === target.id ? null : current))
    }
  }

  function handleUserCreated(newUser: User) {
    setUsers((prev) => sortUsers([newUser, ...prev.filter((u) => u.id !== newUser.id)]))
    setFlashId(newUser.id)
    globalThis.setTimeout(() => {
      setFlashId((current) => (current === newUser.id ? null : current))
    }, 2000)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Users</h2>
          <p className="text-muted-foreground text-sm">
            Manage user roles. SSO users get their role from the identity provider on every login.
          </p>
        </div>
        <Button
          type="button"
          onClick={() => setIsCreateOpen(true)}
          className="gap-2"
        >
          <Plus className="h-4 w-4" />
          Create user
        </Button>
      </div>

      {error && (
        <Card className="p-4 border-destructive/50">
          <p role="alert" className="text-destructive text-sm">{error}</p>
        </Card>
      )}

      <div className="flex items-center gap-2">
        <input
          id="show-deactivated"
          type="checkbox"
          checked={showInactive}
          onChange={(e) => setShowInactive(e.target.checked)}
          className="h-4 w-4 rounded border-input"
        />
        <Label htmlFor="show-deactivated" className="text-sm font-normal cursor-pointer">
          Show deactivated users
        </Label>
      </div>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <p className="text-muted-foreground text-sm">Loading users...</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Email</th>
                  <th className="px-4 py-3 text-left font-medium">Name</th>
                  <th className="px-4 py-3 text-left font-medium">Role</th>
                  <th className="px-4 py-3 text-left font-medium">Provider</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3 text-left font-medium w-20"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {users.map((u) => {
                  const isLocal = u.has_password
                  const isSelf = currentUser?.id === u.id
                  const isPending = pendingId === u.id
                  const showFlash = flashId === u.id
                  const selectDisabled = isSelf || isPending
                  const selectTitle = isSelf
                    ? "You can't change your own role"
                    : undefined
                  const toggleDisabled = isSelf || isPending || !isLocal
                  let toggleTitle: string
                  if (isSelf) toggleTitle = "You can't deactivate yourself"
                  else if (isLocal) toggleTitle = u.is_active ? 'Deactivate user' : 'Activate user'
                  else toggleTitle = 'Status is managed by your identity provider'
                  return (
                    <tr key={u.id} className="hover:bg-muted/40 transition-colors">
                      <td className="px-4 py-3 font-mono text-xs">{u.email}</td>
                      <td className="px-4 py-3">
                        {u.full_name ?? <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="px-4 py-3">
                        {isLocal ? (
                          <select
                            value={u.role}
                            onChange={(e) => handleRoleChange(u, e.target.value as UserRole)}
                            disabled={selectDisabled}
                            title={selectTitle}
                            aria-label={`Role for ${u.email}`}
                            className="flex h-9 w-full max-w-[14rem] rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {ROLE_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>{opt.label}</option>
                            ))}
                          </select>
                        ) : (
                          <Badge
                            variant="outline"
                            title="Role is managed by your identity provider"
                          >
                            {ROLE_LABELS[u.role]}
                          </Badge>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={isLocal ? 'default' : 'outline'}>
                          {isLocal ? 'Local' : 'SSO'}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={u.is_active ? 'default' : 'outline'}>
                          {u.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => handleToggleActive(u)}
                            disabled={toggleDisabled}
                            title={toggleTitle}
                            aria-label={toggleTitle}
                          >
                            {u.is_active ? (
                              <UserX className="h-4 w-4" />
                            ) : (
                              <UserCheck className="h-4 w-4" />
                            )}
                          </Button>
                          {showFlash && (
                            <Check
                              className="h-4 w-4 text-green-600"
                              aria-label="User updated"
                            />
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <CreateUserDialog
        open={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onCreated={handleUserCreated}
      />
    </div>
  )
}

interface CreateUserDialogProps {
  open: boolean
  onClose: () => void
  onCreated: (user: User) => void
}

function CreateUserDialog({ open, onClose, onCreated }: Readonly<CreateUserDialogProps>) {
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('risk_owner')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setEmail('')
      setFullName('')
      setPassword('')
      setRole('risk_owner')
      setError(null)
      setIsSubmitting(false)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !isSubmitting) onClose()
    }
    globalThis.addEventListener('keydown', onKey)
    return () => globalThis.removeEventListener('keydown', onKey)
  }, [open, isSubmitting, onClose])

  if (!open) return null

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (isSubmitting) return
    setError(null)
    setIsSubmitting(true)
    try {
      const created = await usersApi.create({
        email: email.trim(),
        password,
        full_name: fullName.trim() ? fullName.trim() : null,
        role,
      })
      onCreated(created)
      onClose()
    } catch (err) {
      if (err instanceof ApiError) setError(err.message)
      else setError('Could not create user. Try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <dialog
        open
        className="static m-0 w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg"
        aria-modal="true"
        aria-labelledby="create-user-dialog-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="create-user-dialog-title" className="text-lg font-semibold">
              Create user
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Create a local user account. SSO users are provisioned automatically on login.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="text-muted-foreground hover:text-foreground disabled:opacity-50"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="create-user-email">Email</Label>
            <Input
              id="create-user-email"
              type="email"
              required
              autoComplete="off"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isSubmitting}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="create-user-full-name">Full name</Label>
            <Input
              id="create-user-full-name"
              type="text"
              autoComplete="off"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              disabled={isSubmitting}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="create-user-password">Password</Label>
            <Input
              id="create-user-password"
              type="password"
              required
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isSubmitting}
            />
            <p className="text-xs text-muted-foreground">
              At least 12 characters, with uppercase, lowercase, digit, and special character.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="create-user-role">Role</Label>
            <select
              id="create-user-role"
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
              disabled={isSubmitting}
              className="flex h-9 w-full max-w-[14rem] rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              {ROLE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3">
              <p role="alert" className="text-sm text-destructive">{error}</p>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting || !email.trim() || !password}
            >
              {isSubmitting ? 'Creating…' : 'Create user'}
            </Button>
          </div>
        </form>
      </dialog>
    </div>
  )
}
