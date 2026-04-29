/**
 * Risk create / edit form — one component, two modes.
 *
 * Mode is passed as a prop from App.tsx routing:
 *   /risks/new            → mode="create"  — blank form, POST on submit
 *   /risks/:riskId/edit   → mode="edit"    — pre-filled form, PUT on submit
 *
 * Why one component for both?
 *   The fields, validation, and submission logic are 90% identical. Keeping
 *   them together means a field added to create automatically appears in edit.
 *   The only differences are: the HTTP method, the initial values, and the
 *   page title — all gated on the `mode` prop.
 *
 * Likelihood / Impact scale (NIST 800-30):
 *   1 = Very Low   2 = Low   3 = Moderate   4 = High   5 = Very High
 *   Score = likelihood * impact  (range 1-25)
 */
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { risksApi } from '@/services/api'
import type { Risk, RiskStatus } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ArrowLeft } from 'lucide-react'

// ---- Constants --------------------------------------------------------------

const CATEGORIES = [
  'Technical',
  'Compliance',
  'Operational',
  'Strategic',
  'Financial',
  'Reputational',
]

const STATUS_OPTIONS: { value: RiskStatus; label: string }[] = [
  { value: 'open',        label: 'Open' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'mitigated',   label: 'Mitigated' },
  { value: 'accepted',    label: 'Accepted' },
  { value: 'closed',      label: 'Closed' },
]

const LIKELIHOOD_LABELS: Record<number, string> = {
  1: '1 — Very Low',
  2: '2 — Low',
  3: '3 — Moderate',
  4: '4 — High',
  5: '5 — Very High',
}

// ---- Types ------------------------------------------------------------------

interface FormState {
  title: string
  category: string
  description: string
  threat_source: string
  threat_event: string
  vulnerability: string
  affected_asset: string
  likelihood: string   // stored as string for <select> binding; parsed to int on submit
  impact: string
  status: RiskStatus | ''
}

const EMPTY_FORM: FormState = {
  title: '',
  category: '',
  description: '',
  threat_source: '',
  threat_event: '',
  vulnerability: '',
  affected_asset: '',
  likelihood: '',
  impact: '',
  status: '',
}

// ---- Component --------------------------------------------------------------

interface RiskFormPageProps {
  mode: 'create' | 'edit'
}

export default function RiskFormPage({ mode }: RiskFormPageProps) {
  const navigate = useNavigate()
  const { riskId } = useParams<{ riskId: string }>()

  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [isLoading, setIsLoading] = useState(mode === 'edit')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // In edit mode: fetch the existing risk and populate the form.
  useEffect(() => {
    if (mode !== 'edit' || !riskId) return

    risksApi.get(riskId)
      .then((risk: Risk) => {
        const latest = risk.assessments[0]
        setForm({
          title:          risk.title,
          category:       risk.category ?? '',
          description:    risk.description ?? '',
          threat_source:  risk.threat_source ?? '',
          threat_event:   risk.threat_event ?? '',
          vulnerability:  risk.vulnerability ?? '',
          affected_asset: risk.affected_asset ?? '',
          likelihood:     latest ? String(latest.likelihood) : '',
          impact:         latest ? String(latest.impact) : '',
          status:         risk.status,
        })
      })
      .catch(() => setError('Could not load risk. It may have been deleted.'))
      .finally(() => setIsLoading(false))
  }, [mode, riskId])

  // Generic field updater — works for any input/select/textarea.
  function setField(field: keyof FormState) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }))
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)

    // Build the payload — omit blank optional fields rather than sending empty strings.
    const payload = {
      title:          form.title.trim(),
      ...(form.category      && { category:       form.category }),
      ...(form.description   && { description:    form.description.trim() }),
      ...(form.threat_source && { threat_source:  form.threat_source.trim() }),
      ...(form.threat_event  && { threat_event:   form.threat_event.trim() }),
      ...(form.vulnerability && { vulnerability:  form.vulnerability.trim() }),
      ...(form.affected_asset && { affected_asset: form.affected_asset.trim() }),
      // Status only included in edit mode — new risks always start as 'open'.
      ...(mode === 'edit' && form.status && { status: form.status }),
      // Only include likelihood/impact if both are set — a partial score is meaningless.
      ...(form.likelihood && form.impact && {
        likelihood: Number(form.likelihood),
        impact:     Number(form.impact),
      }),
    }

    try {
      if (mode === 'create') {
        const created = await risksApi.create(payload)
        navigate(`/risks/${created.risk_id}`, { replace: true })
      } else {
        await risksApi.update(riskId!, payload)
        navigate(`/risks/${riskId}`, { replace: true })
      }
    } catch {
      setError('Failed to save. Please check your inputs and try again.')
      setIsSubmitting(false)
    }
  }

  // ---- Render ---------------------------------------------------------------

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <p className="text-muted-foreground text-sm">Loading risk...</p>
      </div>
    )
  }

  return (
    <div className="max-w-2xl space-y-6">

      {/* Back link + title */}
      <div>
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
        >
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
        <h1 className="text-2xl font-bold tracking-tight">
          {mode === 'create' ? 'New risk' : 'Edit risk'}
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          {mode === 'create'
            ? 'Log a new risk to the register.'
            : 'Update the risk details below.'}
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-8" noValidate>

        {/* ---- Core fields ---- */}
        <section className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Core details
          </h2>

          <div className="space-y-2">
            <Label htmlFor="title">Title <span className="text-destructive">*</span></Label>
            <Input
              id="title"
              required
              placeholder="e.g. No MFA on admin accounts"
              value={form.title}
              onChange={setField('title')}
              disabled={isSubmitting}
            />
          </div>

          {/* Status — edit mode only; new risks always start as 'open' */}
          {mode === 'edit' && (
            <div className="space-y-2">
              <Label htmlFor="status">Status</Label>
              <select
                id="status"
                value={form.status}
                onChange={setField('status')}
                disabled={isSubmitting}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              >
                {STATUS_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="category">Category</Label>
            <select
              id="category"
              value={form.category}
              onChange={setField('category')}
              disabled={isSubmitting}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            >
              <option value="">Select a category</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              placeholder="Describe the risk in plain language."
              value={form.description}
              onChange={setField('description')}
              disabled={isSubmitting}
              rows={3}
            />
          </div>
        </section>

        {/* ---- NIST 800-30 fields ---- */}
        <section className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            NIST 800-30 details
          </h2>
          <p className="text-xs text-muted-foreground">
            These fields describe the risk in structured NIST terms. All optional,
            but completing them improves report quality.
          </p>

          <div className="space-y-2">
            <Label htmlFor="threat_source">Threat source</Label>
            <Input
              id="threat_source"
              placeholder="e.g. External adversary, Insider threat, Natural disaster"
              value={form.threat_source}
              onChange={setField('threat_source')}
              disabled={isSubmitting}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="threat_event">Threat event</Label>
            <Input
              id="threat_event"
              placeholder="e.g. Phishing attack targeting credentials"
              value={form.threat_event}
              onChange={setField('threat_event')}
              disabled={isSubmitting}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="vulnerability">Vulnerability</Label>
            <Textarea
              id="vulnerability"
              placeholder="e.g. MFA not enforced on privileged accounts"
              value={form.vulnerability}
              onChange={setField('vulnerability')}
              disabled={isSubmitting}
              rows={2}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="affected_asset">Affected asset</Label>
            <Input
              id="affected_asset"
              placeholder="e.g. Customer PII database, Azure admin portal"
              value={form.affected_asset}
              onChange={setField('affected_asset')}
              disabled={isSubmitting}
            />
          </div>
        </section>

        {/* ---- Scoring ---- */}
        <section className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Initial score
          </h2>
          <p className="text-xs text-muted-foreground">
            Both fields must be set together. Score = likelihood x impact (1-25).
            You can add more assessments later from the risk detail page.
          </p>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="likelihood">Likelihood</Label>
              <select
                id="likelihood"
                value={form.likelihood}
                onChange={setField('likelihood')}
                disabled={isSubmitting}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              >
                <option value="">Not set</option>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>{LIKELIHOOD_LABELS[n]}</option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="impact">Impact</Label>
              <select
                id="impact"
                value={form.impact}
                onChange={setField('impact')}
                disabled={isSubmitting}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              >
                <option value="">Not set</option>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>{LIKELIHOOD_LABELS[n]}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Live score preview */}
          {form.likelihood && form.impact && (
            <p className="text-sm text-muted-foreground">
              Score preview:{' '}
              <span className="font-semibold text-foreground">
                {Number(form.likelihood) * Number(form.impact)}
              </span>
              {' '}({Number(form.likelihood)} x {Number(form.impact)})
            </p>
          )}
        </section>

        {error && (
          <p role="alert" className="text-sm text-destructive">{error}</p>
        )}

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={isSubmitting || !form.title.trim()}>
            {isSubmitting
              ? 'Saving...'
              : mode === 'create' ? 'Create risk' : 'Save changes'}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => navigate(-1)}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
        </div>

      </form>
    </div>
  )
}
