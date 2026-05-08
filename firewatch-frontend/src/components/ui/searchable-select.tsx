import { useEffect, useMemo, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

export interface SearchableSelectProps {
  id?: string
  value: string
  onChange: (value: string) => void
  options: string[]
  placeholder?: string
  disabled?: boolean
  emptyText?: string
}

export function SearchableSelect({
  id,
  value,
  onChange,
  options,
  placeholder = 'Select...',
  disabled = false,
  emptyText = 'No matches',
}: SearchableSelectProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter((o) => o.toLowerCase().includes(q))
  }, [options, query])

  useEffect(() => {
    if (!open) return
    function onMouseDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false)
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        setHighlight((h) => Math.min(filtered.length, h + 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setHighlight((h) => Math.max(0, h - 1))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        if (highlight === 0) {
          onChange('')
          setOpen(false)
        } else {
          const picked = filtered[highlight - 1]
          if (picked !== undefined) {
            onChange(picked)
            setOpen(false)
          }
        }
      }
    }
    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, filtered, highlight, onChange])

  useEffect(() => {
    if (open) {
      setQuery('')
      setHighlight(0)
      requestAnimationFrame(() => searchRef.current?.focus())
    }
  }, [open])

  function pick(option: string) {
    onChange(option)
    setOpen(false)
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        id={id}
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm',
          'focus:outline-none focus:ring-2 focus:ring-ring',
          'disabled:cursor-not-allowed disabled:opacity-50',
        )}
      >
        <span className={cn('truncate', !value && 'text-muted-foreground')}>
          {value || placeholder}
        </span>
        <svg
          aria-hidden="true"
          className="ml-2 h-4 w-4 shrink-0 opacity-50"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 w-full rounded-md border border-input bg-background shadow-md">
          <div className="p-2 border-b border-border">
            <input
              ref={searchRef}
              type="text"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setHighlight(0) }}
              placeholder="Search..."
              className="flex h-8 w-full rounded-md border border-input bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <ul className="max-h-60 overflow-y-auto py-1">
            <li>
              <button
                type="button"
                onMouseEnter={() => setHighlight(0)}
                onClick={() => pick('')}
                className={cn(
                  'flex w-full items-center px-3 py-2 text-left text-sm text-muted-foreground italic',
                  highlight === 0 && 'bg-accent',
                )}
              >
                (any) — clear selection
              </button>
            </li>
            {filtered.length === 0 ? (
              <li className="px-3 py-2 text-sm text-muted-foreground">{emptyText}</li>
            ) : (
              filtered.map((opt, idx) => (
                <li key={opt}>
                  <button
                    type="button"
                    onMouseEnter={() => setHighlight(idx + 1)}
                    onClick={() => pick(opt)}
                    className={cn(
                      'flex w-full items-center px-3 py-2 text-left text-sm font-mono',
                      highlight === idx + 1 && 'bg-accent',
                      value === opt && 'font-semibold',
                    )}
                  >
                    {opt}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  )
}
