import { useCallback, useEffect, useRef, useState, type SyntheticEvent } from 'react'
import { FileUp, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { ApiError, frameworksApi } from '@/services/api'
import { useAuth } from '@/context/AuthContext'
import type { ControlFramework, FrameworkImportResult } from '@/types'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

function formatDate(iso: string | null | undefined): React.ReactNode {
  if (!iso) return <span className="text-muted-foreground">—</span>
  return new Date(iso).toLocaleString()
}

function resultMessage(r: FrameworkImportResult): string {
  const label = r.version ? `${r.framework_name} ${r.version}` : r.framework_name
  return `Imported ${label}: ${r.created} added, ${r.updated} updated`
}

// Maps known import errors to friendlier copy; falls back to the server message.
function importErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 502) return "Couldn't fetch from that URL."
    if (err.status === 413) return 'File too large.'
    return err.message
  }
  return 'Could not import, try again.'
}

function DeleteFrameworkDialog({
  open,
  isDeleting,
  errorMessage,
  frameworkName,
  onConfirm,
  onClose,
}: Readonly<{
  open: boolean
  isDeleting: boolean
  errorMessage: string | null
  frameworkName: string
  onConfirm: () => void
  onClose: () => void
}>) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    if (open) ref.current?.showModal()
  }, [open])

  function handleCancelEvent(e: SyntheticEvent<HTMLDialogElement>) {
    if (isDeleting) e.preventDefault()
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="delete-framework-dialog-title"
      onCancel={handleCancelEvent}
      onClose={onClose}
      className="bg-background rounded-lg border shadow-lg m-auto max-w-[min(28rem,calc(100vw-2rem))] w-full p-6 space-y-4 backdrop:bg-black/50"
    >
      <h3 id="delete-framework-dialog-title" className="font-semibold text-base">
        Delete {frameworkName}?
      </h3>
      <p className="text-sm text-muted-foreground">
        This removes the framework and its controls. This cannot be undone.
      </p>
      {errorMessage && (
        <p role="alert" className="text-sm text-destructive">{errorMessage}</p>
      )}
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={isDeleting}
          onClick={() => ref.current?.close()}
        >
          Cancel
        </Button>
        <Button
          variant="destructive"
          size="sm"
          disabled={isDeleting}
          onClick={onConfirm}
        >
          {isDeleting ? 'Deleting…' : 'Delete'}
        </Button>
      </div>
    </dialog>
  )
}

type SourceMode = 'file' | 'url'

// Shared create/edit dialog. `framework` null → create mode; otherwise edit mode.
function FrameworkDialog({
  open,
  framework,
  onClose,
  onSuccess,
}: Readonly<{
  open: boolean
  framework: ControlFramework | null
  onClose: () => void
  onSuccess: (message: string) => void
}>) {
  const ref = useRef<HTMLDialogElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const isEdit = framework !== null

  // Shared form fields.
  const [name, setName] = useState('')
  const [version, setVersion] = useState('')
  const [description, setDescription] = useState('')

  // Source (file or URL) — used by create, and by edit's "replace controls" section.
  const [sourceMode, setSourceMode] = useState<SourceMode>('file')
  const [file, setFile] = useState<File | null>(null)
  const [url, setUrl] = useState('')

  // Per-operation busy/error state so a reimport failure doesn't clobber a
  // successful metadata save (and vice versa).
  const [isSaving, setIsSaving] = useState(false)
  const [isReplacing, setIsReplacing] = useState(false)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [sourceError, setSourceError] = useState<string | null>(null)

  // Reset fields whenever the dialog (re)opens.
  useEffect(() => {
    if (!open) return
    setName(framework?.name ?? '')
    setVersion(framework?.version ?? '')
    setDescription(framework?.description ?? '')
    setSourceMode('file')
    setFile(null)
    setUrl('')
    setMetaError(null)
    setSourceError(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
    ref.current?.showModal()
  }, [open, framework])

  const isBusy = isSaving || isReplacing

  function handleCancelEvent(e: SyntheticEvent<HTMLDialogElement>) {
    if (isBusy) e.preventDefault()
  }

  function handleSelectFile(e: React.ChangeEvent<HTMLInputElement>) {
    setFile(e.target.files?.[0] ?? null)
    setSourceError(null)
  }

  // Create mode: import from the chosen source (file preferred, else URL).
  async function handleCreate() {
    if (isBusy) return
    if (!file && !url.trim()) {
      setSourceError('Choose a file or enter a URL.')
      return
    }
    setIsSaving(true)
    setSourceError(null)
    try {
      const res = file
        ? await frameworksApi.importFrameworkFile(file, {
            framework_name: name.trim() || undefined,
            version: version.trim() || undefined,
          })
        : await frameworksApi.importFrameworkFromUrl({
            url: url.trim(),
            framework_name: name.trim() || null,
            version: version.trim() || null,
          })
      onSuccess(resultMessage(res))
      ref.current?.close()
    } catch (err) {
      setSourceError(importErrorMessage(err))
    } finally {
      setIsSaving(false)
    }
  }

  // Edit mode: save metadata only (does not touch controls).
  async function handleSaveMetadata() {
    if (!framework || isBusy) return
    setIsSaving(true)
    setMetaError(null)
    try {
      await frameworksApi.updateFramework(framework.id, {
        name: name.trim() || undefined,
        version: version.trim() || undefined,
        description: description.trim() || undefined,
      })
      onSuccess(`Updated ${name.trim() || framework.name}`)
      ref.current?.close()
    } catch (err) {
      // 409 = name collision; surface the server message verbatim.
      setMetaError(err instanceof ApiError ? err.message : 'Could not save changes. Try again.')
    } finally {
      setIsSaving(false)
    }
  }

  // Edit mode: destructive — replaces all controls from a new file/URL.
  async function handleReplaceSource() {
    if (!framework || isBusy) return
    if (!file && !url.trim()) {
      setSourceError('Choose a file or enter a URL.')
      return
    }
    setIsReplacing(true)
    setSourceError(null)
    try {
      const res = file
        ? await frameworksApi.reimportFrameworkFile(framework.id, file, {
            version: version.trim() || undefined,
          })
        : await frameworksApi.reimportFrameworkFromUrl(framework.id, {
            url: url.trim(),
            version: version.trim() || undefined,
          })
      onSuccess(resultMessage(res))
      ref.current?.close()
    } catch (err) {
      // 409 = controls mapped to risks; the server detail is actionable.
      setSourceError(importErrorMessage(err))
    } finally {
      setIsReplacing(false)
    }
  }

  const fileInputId = 'framework-dialog-file'
  const urlInputId = 'framework-dialog-url'

  function renderSourcePicker() {
    return (
      <>
        <div className="flex gap-2">
          <Button
            type="button"
            variant={sourceMode === 'file' ? 'default' : 'outline'}
            size="sm"
            disabled={isBusy}
            onClick={() => { setSourceMode('file'); setSourceError(null) }}
          >
            Upload file
          </Button>
          <Button
            type="button"
            variant={sourceMode === 'url' ? 'default' : 'outline'}
            size="sm"
            disabled={isBusy}
            onClick={() => { setSourceMode('url'); setSourceError(null) }}
          >
            From URL
          </Button>
        </div>

        {sourceMode === 'file' ? (
          <div>
            <label
              htmlFor={fileInputId}
              className="flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-input bg-background px-4 py-6 hover:bg-accent/50"
            >
              <FileUp className="h-5 w-5 text-muted-foreground" />
              <div className="flex flex-col">
                <span className="text-sm font-medium">
                  {file ? file.name : 'Choose a .csv or .json file'}
                </span>
                <span className="text-xs text-muted-foreground">
                  {file ? `${(file.size / 1024).toFixed(1)} KB` : 'Click to browse. Up to 25 MB.'}
                </span>
              </div>
            </label>
            <input
              ref={fileInputRef}
              id={fileInputId}
              type="file"
              accept=".csv,.json"
              onChange={handleSelectFile}
              disabled={isBusy}
              className="sr-only"
            />
          </div>
        ) : (
          <div className="space-y-2">
            <Label htmlFor={urlInputId}>URL</Label>
            <Input
              id={urlInputId}
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={isBusy}
              placeholder="https://example.com/controls.csv"
            />
          </div>
        )}
      </>
    )
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="framework-dialog-title"
      onCancel={handleCancelEvent}
      onClose={onClose}
      className="bg-background rounded-lg border shadow-lg m-auto max-w-[min(32rem,calc(100vw-2rem))] w-full p-6 space-y-4 backdrop:bg-black/50"
    >
      <h3 id="framework-dialog-title" className="font-semibold text-base">
        {isEdit ? `Edit ${framework.name}` : 'New framework'}
      </h3>

      <div className="space-y-2">
        <Label htmlFor="framework-dialog-name">Framework name (optional)</Label>
        <Input
          id="framework-dialog-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={isBusy}
          placeholder="e.g. NIST 800-53"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="framework-dialog-version">Version (optional)</Label>
        <Input
          id="framework-dialog-version"
          type="text"
          value={version}
          onChange={(e) => setVersion(e.target.value)}
          disabled={isBusy}
          placeholder="e.g. Rev 5"
        />
      </div>

      {isEdit && (
        <div className="space-y-2">
          <Label htmlFor="framework-dialog-description">Description (optional)</Label>
          <Input
            id="framework-dialog-description"
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={isBusy}
            placeholder="Short description"
          />
        </div>
      )}

      {isEdit ? (
        <>
          {metaError && <p role="alert" className="text-sm text-destructive">{metaError}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" disabled={isBusy} onClick={() => ref.current?.close()}>
              Cancel
            </Button>
            <Button size="sm" disabled={isBusy} onClick={() => { void handleSaveMetadata() }}>
              {isSaving ? 'Saving…' : 'Save changes'}
            </Button>
          </div>

          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-4 space-y-3">
            <div>
              <h4 className="text-sm font-semibold text-destructive">Replace controls from new source</h4>
              <p className="mt-1 text-xs text-muted-foreground">
                Replacing the source overwrites all controls. Blocked if any control is mapped to a risk.
              </p>
            </div>
            {renderSourcePicker()}
            {sourceError && <p role="alert" className="text-sm text-destructive">{sourceError}</p>}
            <div className="flex justify-end">
              <Button
                type="button"
                variant="destructive"
                size="sm"
                className="gap-2"
                disabled={isBusy || (!file && !url.trim())}
                onClick={() => { void handleReplaceSource() }}
              >
                <RefreshCw className="h-4 w-4" />
                {isReplacing ? 'Replacing…' : 'Replace controls'}
              </Button>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="space-y-3">
            <Label>Source</Label>
            {renderSourcePicker()}
          </div>
          {sourceError && <p role="alert" className="text-sm text-destructive">{sourceError}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" disabled={isBusy} onClick={() => ref.current?.close()}>
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={isBusy || (!file && !url.trim())}
              onClick={() => { void handleCreate() }}
            >
              {isSaving ? 'Importing…' : 'Create'}
            </Button>
          </div>
        </>
      )}
    </dialog>
  )
}

export default function SettingsFrameworksPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [frameworks, setFrameworks] = useState<ControlFramework[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [success, setSuccess] = useState<string | null>(null)

  // Create/edit dialog. `editing` null + open=true → create; otherwise edit.
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<ControlFramework | null>(null)

  // Delete state.
  const [frameworkToDelete, setFrameworkToDelete] = useState<ControlFramework | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const fetchFrameworks = useCallback(() => {
    setIsLoading(true)
    setLoadError(null)
    frameworksApi
      .getFrameworks()
      .then((data) => setFrameworks(data))
      .catch((err) => {
        if (err instanceof ApiError) setLoadError(err.message)
        else setLoadError('Could not load frameworks. Try again.')
      })
      .finally(() => setIsLoading(false))
  }, [])

  useEffect(() => { fetchFrameworks() }, [fetchFrameworks])

  function openCreate() {
    setEditing(null)
    setDialogOpen(true)
  }

  function openEdit(f: ControlFramework) {
    setEditing(f)
    setDialogOpen(true)
  }

  function handleDialogSuccess(message: string) {
    setSuccess(message)
    setDialogOpen(false)
    setEditing(null)
    fetchFrameworks()
  }

  function askDeleteFramework(f: ControlFramework) {
    setDeleteError(null)
    setFrameworkToDelete(f)
  }

  async function handleConfirmDelete() {
    if (!frameworkToDelete || isDeleting) return
    setIsDeleting(true)
    setDeleteError(null)
    setSuccess(null)
    try {
      await frameworksApi.deleteFramework(frameworkToDelete.id)
      setSuccess(`Deleted ${frameworkToDelete.name}`)
      setFrameworkToDelete(null)
      fetchFrameworks()
    } catch (err) {
      // 409 means the framework's controls are mapped to risks — the server's
      // detail message is user-actionable ("unmap first"), so surface it as-is.
      // 404/other: surface the server message too. Keep the dialog open so the
      // user can read the error and cancel or retry.
      if (err instanceof ApiError) setDeleteError(err.message)
      else setDeleteError('Could not delete framework. Try again.')
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Frameworks</h2>
        <p className="text-muted-foreground text-sm">
          Manage the compliance control catalog. Create a new framework or edit an
          existing one from a file upload or a URL.
        </p>
      </div>

      {success && (
        <Card className="p-4 border-green-200 bg-green-50 dark:border-green-900/50 dark:bg-green-950/40">
          <p role="status" className="text-sm font-medium text-green-800 dark:text-green-200">
            ✓ {success}
          </p>
        </Card>
      )}

      <Card className="overflow-hidden">
        <div className="border-b px-4 py-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Frameworks</h3>
          {isAdmin && (
            <Button type="button" size="sm" className="gap-2" onClick={openCreate}>
              <Plus className="h-4 w-4" />
              New
            </Button>
          )}
        </div>
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <p className="text-muted-foreground text-sm">Loading frameworks...</p>
          </div>
        ) : loadError ? (
          <div className="px-4 py-6">
            <p role="alert" className="text-sm text-destructive">{loadError}</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Name</th>
                  <th className="px-4 py-3 text-left font-medium">Version</th>
                  <th className="px-4 py-3 text-left font-medium">Source</th>
                  <th className="px-4 py-3 text-left font-medium">Last imported</th>
                  {isAdmin && (
                    <th className="px-4 py-3 text-right font-medium">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {frameworks.length === 0 ? (
                  <tr>
                    <td colSpan={isAdmin ? 5 : 4} className="px-4 py-10 text-center text-muted-foreground">
                      No frameworks yet. Use “New” to import one.
                    </td>
                  </tr>
                ) : (
                  frameworks.map((f) => (
                    <tr key={f.id} className="hover:bg-muted/40 transition-colors">
                      <td className="px-4 py-3 font-medium">{f.name}</td>
                      <td className="px-4 py-3">
                        {f.version ?? <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="px-4 py-3 max-w-xs truncate">
                        {f.source_url ? (
                          <a
                            href={f.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary hover:underline"
                            title={f.source_url}
                          >
                            {f.source_url}
                          </a>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">{formatDate(f.last_imported_at)}</td>
                      {isAdmin && (
                        <td className="px-4 py-3 text-right">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            aria-label={`Edit ${f.name}`}
                            onClick={() => openEdit(f)}
                            className="text-muted-foreground hover:text-foreground"
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            aria-label={`Delete ${f.name}`}
                            onClick={() => askDeleteFramework(f)}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {isAdmin && dialogOpen && (
        <FrameworkDialog
          open={dialogOpen}
          framework={editing}
          onClose={() => {
            setDialogOpen(false)
            setEditing(null)
          }}
          onSuccess={handleDialogSuccess}
        />
      )}

      {isAdmin && frameworkToDelete && (
        <DeleteFrameworkDialog
          open={frameworkToDelete !== null}
          isDeleting={isDeleting}
          errorMessage={deleteError}
          frameworkName={frameworkToDelete.name}
          onConfirm={() => { void handleConfirmDelete() }}
          onClose={() => {
            setFrameworkToDelete(null)
            setDeleteError(null)
          }}
        />
      )}
    </div>
  )
}
