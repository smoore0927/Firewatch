import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_VIEW,
  parseRegisterView,
  registerPath,
  registerViewToParams,
  rememberRegisterSearch,
  type RegisterView,
} from '@/lib/register-view'

function parse(query: string): RegisterView {
  return parseRegisterView(new URLSearchParams(query))
}

describe('parseRegisterView', () => {
  it('returns the defaults for an empty query', () => {
    expect(parse('')).toEqual(DEFAULT_VIEW)
  })

  it('reads every param', () => {
    expect(parse('page=3&size=50&q=phish&status=open&category=Technical&owner=7&severity=high&due=1&sort=score&order=desc'))
      .toEqual({
        page: 2,
        pageSize: 50,
        search: 'phish',
        status: 'open',
        category: 'Technical',
        owner: '7',
        severity: 'high',
        dueForReview: true,
        sort: 'score',
        order: 'desc',
      })
  })

  it.each([
    ['page=0'], ['page=-2'], ['page=abc'], ['page=2.5'],
    ['size=7'], ['size=200'],
    ['status=bogus'], ['category=Nope'],
    ['owner=abc'], ['owner=0'], ['owner=-3'], ['owner=1.5'],
    ['severity=extreme'], ['sort=bogus'], ['order=up'], ['due=true'],
  ])('falls back to the default for %s', (query) => {
    expect(parse(query)).toEqual(DEFAULT_VIEW)
  })

  it('trims the search', () => {
    expect(parse('q=%20%20phish%20').search).toBe('phish')
  })
})

describe('registerViewToParams', () => {
  it('leaves out everything at its default', () => {
    expect(registerViewToParams(DEFAULT_VIEW).toString()).toBe('')
  })

  it('round-trips a non-default view', () => {
    const view: RegisterView = {
      page: 4,
      pageSize: 100,
      search: '50% off_',
      status: 'in_progress',
      category: 'Compliance',
      owner: '12',
      severity: 'unscored',
      dueForReview: true,
      sort: 'next_review',
      order: 'desc',
    }
    expect(parseRegisterView(registerViewToParams(view))).toEqual(view)
  })

  it('writes the page one-based', () => {
    expect(registerViewToParams({ ...DEFAULT_VIEW, page: 1 }).get('page')).toBe('2')
  })
})

describe('registerPath', () => {
  beforeEach(() => sessionStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('is the bare register when nothing has been remembered', () => {
    expect(registerPath()).toBe('/risks')
  })

  it('returns to the remembered view', () => {
    rememberRegisterSearch('?status=open&page=2')
    expect(registerPath()).toBe('/risks?status=open&page=2')
  })

  it('goes to the default view once the remembered view is the default', () => {
    rememberRegisterSearch('?page=2')
    rememberRegisterSearch('')
    expect(registerPath()).toBe('/risks')
  })

  it('ignores a stored value that is not a query string', () => {
    sessionStorage.setItem('firewatch.register.search', '//evil.example.com')
    expect(registerPath()).toBe('/risks')
  })

  it('falls back to the bare register when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(() => rememberRegisterSearch('?page=2')).not.toThrow()
    expect(registerPath()).toBe('/risks')
  })
})
