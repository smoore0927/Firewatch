/**
 * The risk register's view state (filters, search, sort, page) as URL query
 * params, so a page of the register can be refreshed, shared, and returned to.
 */
import { CATEGORIES, RISK_STATUS_LABELS, type Category } from '@/lib/constants'
import type { RiskSeverityParam, RiskSortKey, RiskSortOrder, RiskStatus } from '@/types'

export interface RegisterView {
  /** Zero-based; the URL carries it one-based. */
  page: number
  pageSize: number
  search: string
  status: RiskStatus | 'all'
  category: Category | 'all'
  /** An owner's user id as a string, or 'all'. */
  owner: string
  severity: RiskSeverityParam | 'all'
  dueForReview: boolean
  sort: RiskSortKey
  order: RiskSortOrder
}

export const PAGE_SIZES = [25, 50, 100] as const

export const SEVERITY_OPTIONS: { value: RiskSeverityParam; label: string }[] = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
  { value: 'unscored', label: 'Unscored' },
]

const SORT_KEYS: RiskSortKey[] = ['id', 'title', 'category', 'score', 'status', 'owner', 'next_review']

export const DEFAULT_VIEW: RegisterView = {
  page: 0,
  pageSize: PAGE_SIZES[0],
  search: '',
  status: 'all',
  category: 'all',
  owner: 'all',
  severity: 'all',
  dueForReview: false,
  sort: 'title',
  order: 'asc',
}

function oneOf<T extends string>(value: string | null, allowed: readonly T[]): T | undefined {
  return allowed.find((a) => a === value)
}

/** Read a view from the URL. Missing or invalid params fall back to the defaults. */
export function parseRegisterView(params: URLSearchParams): RegisterView {
  const page = Number(params.get('page'))
  const pageSize = Number(params.get('size'))
  const owner = params.get('owner') ?? ''
  return {
    page: Number.isInteger(page) && page >= 1 ? page - 1 : DEFAULT_VIEW.page,
    pageSize: PAGE_SIZES.find((s) => s === pageSize) ?? DEFAULT_VIEW.pageSize,
    search: (params.get('q') ?? '').trim(),
    status: oneOf(params.get('status'), Object.keys(RISK_STATUS_LABELS) as RiskStatus[]) ?? DEFAULT_VIEW.status,
    category: oneOf(params.get('category'), CATEGORIES) ?? DEFAULT_VIEW.category,
    owner: /^[1-9]\d*$/.test(owner) ? owner : DEFAULT_VIEW.owner,
    severity: oneOf(params.get('severity'), SEVERITY_OPTIONS.map((o) => o.value)) ?? DEFAULT_VIEW.severity,
    dueForReview: params.get('due') === '1',
    sort: oneOf(params.get('sort'), SORT_KEYS) ?? DEFAULT_VIEW.sort,
    order: oneOf(params.get('order'), ['asc', 'desc'] as const) ?? DEFAULT_VIEW.order,
  }
}

/** Write a view as URL params, leaving out anything at its default so URLs stay short. */
export function registerViewToParams(view: RegisterView): URLSearchParams {
  const params = new URLSearchParams()
  if (view.search) params.set('q', view.search)
  if (view.status !== 'all') params.set('status', view.status)
  if (view.category !== 'all') params.set('category', view.category)
  if (view.owner !== 'all') params.set('owner', view.owner)
  if (view.severity !== 'all') params.set('severity', view.severity)
  if (view.dueForReview) params.set('due', '1')
  if (view.sort !== DEFAULT_VIEW.sort) params.set('sort', view.sort)
  if (view.order !== DEFAULT_VIEW.order) params.set('order', view.order)
  if (view.pageSize !== DEFAULT_VIEW.pageSize) params.set('size', String(view.pageSize))
  if (view.page > 0) params.set('page', String(view.page + 1))
  return params
}

// The register remembers its last query string for this tab so links back to
// it from a risk (which can be several navigations later, e.g. after an edit)
// return to the same page and filters. Storage can be unavailable; that just
// means the link goes to the default view.
const LAST_SEARCH_KEY = 'firewatch.register.search'

export function rememberRegisterSearch(search: string): void {
  try {
    globalThis.sessionStorage.setItem(LAST_SEARCH_KEY, search)
  } catch {
    // Unavailable storage only loses the convenience.
  }
}

/** Path back to the register as the user last left it in this tab. */
export function registerPath(): string {
  try {
    const search = globalThis.sessionStorage.getItem(LAST_SEARCH_KEY)
    return search?.startsWith('?') ? `/risks${search}` : '/risks'
  } catch {
    return '/risks'
  }
}
