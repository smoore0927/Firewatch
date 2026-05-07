import { useEffect, useRef, useState } from 'react'
import { ApiError, risksApi } from '@/services/api'
import type { ImportResult } from '@/types'
import { Button } from '@/components/ui/button'
import { Download, FileUp, X } from 'lucide-react'

interface Props {
  open: boolean
  onClose: () => void
  onImported: () => void
}

export default function ImportRisksDialog({ open, onClose, onImported }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isDownloadingTemplate, setIsDownloadingTemplate] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Reset state whenever the dialog re-opens so a previous result doesn't linger.
  useEffect(() => {
    if (open) {
      setFile(null)
      setError(null)
      setResult(null)
      setIsUploading(false)
      setIsDownloadingTemplate(false)
    }
  }, [open])

  // Close on Escape for keyboard users.
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !isUploading) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, isUploading, onClose])

  if (!open) return null

  async function handleDownloadTemplate() {
    setIsDownloadingTemplate(true)
    setError(null)
    try {
      await risksApi.downloadTemplate()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not download template, try again.')
    } finally {
      setIsDownloadingTemplate(false)
    }
  }

  async function handleImport() {
    if (!file) return
    setIsUploading(true)
    setError(null)
    try {
      const res = await risksApi.importCsv(file)
      setResult(res)
      // Refresh the risks list as soon as the import succeeds — even if some
      // rows had errors, the `created` ones should appear immediately.
      if (res.created > 0) onImported()
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError('Could not upload, try again.')
      }
    } finally {
      setIsUploading(false)
    }
  }

  function handleDone() {
    onImported()
    onClose()
  }

  function handleSelectFile(e: React.ChangeEvent<HTMLInputElement>) {
    const next = e.target.files?.[0] ?? null
    setFile(next)
    setError(null)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={() => { if (!isUploading) onClose() }}
    >
      <div
        className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="import-dialog-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="import-dialog-title" className="text-lg font-semibold">
              Import risks from CSV
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Upload a CSV file with risk data. Download the template below to see the
              expected format and column headers.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isUploading}
            className="text-muted-foreground hover:text-foreground disabled:opacity-50"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={handleDownloadTemplate}
            disabled={isDownloadingTemplate}
          >
            <Download className="h-4 w-4" />
            {isDownloadingTemplate ? 'Downloading…' : 'Download template (.csv)'}
          </Button>
        </div>

        {/* Result panel replaces the file picker after a successful upload. */}
        {result ? (
          <div className="mt-6 space-y-4">
            <div className="rounded-md border border-green-200 bg-green-50 p-4 dark:border-green-900 dark:bg-green-950">
              <p className="font-medium text-green-800 dark:text-green-200">
                ✓ {result.created} risk{result.created === 1 ? '' : 's'} imported
              </p>
            </div>

            {result.errors.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium">
                  {result.errors.length} row{result.errors.length === 1 ? '' : 's'} had errors
                </p>
                <ul className="max-h-[200px] overflow-y-auto rounded-md border bg-muted/30 p-3 text-xs space-y-1">
                  {result.errors.map((e, i) => (
                    <li key={`${e.row}-${i}`} className="font-mono">
                      Row {e.row}: {e.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex justify-end">
              <Button type="button" onClick={handleDone}>
                Done
              </Button>
            </div>
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            <div>
              <label
                htmlFor="csv-file-input"
                className="flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-input bg-background px-4 py-6 hover:bg-accent/50"
              >
                <FileUp className="h-5 w-5 text-muted-foreground" />
                <div className="flex flex-col">
                  <span className="text-sm font-medium">
                    {file ? file.name : 'Choose a CSV file'}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {file
                      ? `${(file.size / 1024).toFixed(1)} KB`
                      : 'Up to 5 MB. Click to browse.'}
                  </span>
                </div>
              </label>
              <input
                ref={fileInputRef}
                id="csv-file-input"
                type="file"
                accept=".csv,text/csv"
                onChange={handleSelectFile}
                disabled={isUploading}
                className="sr-only"
              />
            </div>

            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                disabled={isUploading}
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={handleImport}
                disabled={!file || isUploading}
              >
                {isUploading ? 'Importing…' : 'Import'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
