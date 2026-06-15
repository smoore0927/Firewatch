import { useEffect, useRef, useState } from 'react'
import { errorMessage, risksApi } from '@/services/api'
import type { ImportResult } from '@/types'
import { Button } from '@/components/ui/button'
import { Modal } from '@/components/ui/modal'
import { Download, FileUp } from 'lucide-react'

interface Props {
  open: boolean
  onClose: () => void
  onImported: () => void
}

export default function ImportRisksDialog({ open, onClose, onImported }: Readonly<Props>) {
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

  async function handleDownloadTemplate() {
    setIsDownloadingTemplate(true)
    setError(null)
    try {
      await risksApi.downloadTemplate()
    } catch (err) {
      setError(errorMessage(err, 'Could not download template, try again.'))
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
      setError(errorMessage(err, 'Could not upload, try again.'))
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
    <Modal
      open={open}
      onClose={onClose}
      busy={isUploading}
      title="Import risks from CSV"
      description={
        <>
          Upload a CSV file with risk data. Download the template below to see the
          expected format and column headers.
          <span className="mt-2 block text-xs">
            Optionally include a <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">created_at</code> column (ISO date, e.g. 2024-01-15) to preserve the original creation date of existing risks. If left blank, it defaults to the upload time.
          </span>
        </>
      }
    >
        <div>
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
            <div className="rounded-md border border-green-200 bg-green-50 p-4 dark:border-green-900/50 dark:bg-green-950/40">
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
                    {file ? file.name : <>Choose a CSV file <span aria-hidden="true" className="text-destructive">*</span></>}
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
                aria-required="true"
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
    </Modal>
  )
}
