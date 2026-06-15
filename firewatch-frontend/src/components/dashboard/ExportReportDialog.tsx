import { useEffect, useState } from 'react'
import { errorMessage, reportsApi } from '@/services/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Modal } from '@/components/ui/modal'

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
}: Readonly<Props>) {
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

  async function handleGenerate() {
    setIsGenerating(true)
    try {
      const data = await reportsApi.getRiskSummary(start, end, includeRisks)
      // The PDF toolchain (jspdf / html2canvas) is heavy and only needed when a
      // report is actually generated, so it is loaded on demand here to keep it
      // out of the dashboard's initial chunk.
      const { generateRiskReportPdf } = await import('@/lib/pdf-report')
      await generateRiskReportPdf(data, { matrixEl, chartEl })
      onClose()
    } catch (err) {
      onError?.(errorMessage(err, 'Could not generate report. Try again.'))
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Export PDF Report" busy={isGenerating} className="max-w-md">
        <div className="space-y-4">
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
    </Modal>
  )
}
