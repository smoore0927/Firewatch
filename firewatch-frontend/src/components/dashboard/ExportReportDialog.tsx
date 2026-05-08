import { useEffect, useState } from 'react'
import { ApiError, reportsApi } from '@/services/api'
import { generateRiskReportPdf } from '@/lib/pdf-report'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { X } from 'lucide-react'

interface Props {
  open: boolean
  onClose: () => void
  defaultStart: string
  defaultEnd: string
  matrixEl: HTMLElement | null
  chartEl: HTMLElement | null
  onError?: (message: string) => void
}

export default function ExportReportDialog({
  open,
  onClose,
  defaultStart,
  defaultEnd,
  matrixEl,
  chartEl,
  onError,
}: Props) {
  const [start, setStart] = useState(defaultStart)
  const [end, setEnd] = useState(defaultEnd)
  const [includeRisks, setIncludeRisks] = useState(true)
  const [isGenerating, setIsGenerating] = useState(false)

  useEffect(() => {
    if (open) {
      setStart(defaultStart)
      setEnd(defaultEnd)
      setIncludeRisks(true)
      setIsGenerating(false)
    }
  }, [open, defaultStart, defaultEnd])

  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !isGenerating) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, isGenerating, onClose])

  if (!open) return null

  async function handleGenerate() {
    setIsGenerating(true)
    try {
      const data = await reportsApi.getRiskSummary(start, end, includeRisks)
      await generateRiskReportPdf(data, { matrixEl, chartEl })
      onClose()
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : 'Could not generate report. Try again.'
      onError?.(message)
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={() => { if (!isGenerating) onClose() }}
    >
      <div
        className="w-full max-w-md rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-report-title"
      >
        <div className="flex items-start justify-between gap-4">
          <h2 id="export-report-title" className="text-lg font-semibold">
            Export PDF Report
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={isGenerating}
            className="text-muted-foreground hover:text-foreground disabled:opacity-50"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="export-start">From</Label>
              <Input
                id="export-start"
                type="date"
                value={start}
                max={end}
                onChange={(e) => setStart(e.target.value)}
                disabled={isGenerating}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="export-end">To</Label>
              <Input
                id="export-end"
                type="date"
                value={end}
                min={start}
                onChange={(e) => setEnd(e.target.value)}
                disabled={isGenerating}
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              id="include-risks"
              type="checkbox"
              checked={includeRisks}
              onChange={(e) => setIncludeRisks(e.target.checked)}
              disabled={isGenerating}
              className="h-4 w-4 rounded border-input accent-primary"
            />
            <Label htmlFor="include-risks" className="cursor-pointer">
              Include risks in the register
            </Label>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={isGenerating}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleGenerate}
            disabled={isGenerating}
          >
            {isGenerating ? 'Generating…' : 'Generate PDF'}
          </Button>
        </div>
      </div>
    </div>
  )
}
