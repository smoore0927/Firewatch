import { useCallback, useEffect, useRef, useState } from 'react'

export interface UseResizableSidebarOptions {
  storageKey: string
  defaultWidth: number
  minWidth: number
  maxWidth: number
}

export interface UseResizableSidebarReturn {
  width: number
  isCollapsed: boolean
  toggleCollapsed: () => void
  startResize: (e: React.MouseEvent) => void
}

function readStoredWidth(key: string, fallback: number, min: number, max: number): number {
  try {
    const raw = window.localStorage.getItem(`${key}.width`)
    if (raw == null) return fallback
    const parsed = Number.parseInt(raw, 10)
    if (Number.isNaN(parsed)) return fallback
    return Math.min(max, Math.max(min, parsed))
  } catch {
    return fallback
  }
}

function readStoredCollapsed(key: string): boolean {
  try {
    return window.localStorage.getItem(`${key}.collapsed`) === 'true'
  } catch {
    return false
  }
}

export function useResizableSidebar(
  options: UseResizableSidebarOptions,
): UseResizableSidebarReturn {
  const { storageKey, defaultWidth, minWidth, maxWidth } = options

  const [storedWidth, setStoredWidth] = useState<number>(() =>
    readStoredWidth(storageKey, defaultWidth, minWidth, maxWidth),
  )
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => readStoredCollapsed(storageKey))

  const storedWidthRef = useRef(storedWidth)
  useEffect(() => {
    storedWidthRef.current = storedWidth
  }, [storedWidth])

  const toggleCollapsed = useCallback(() => {
    setIsCollapsed((prev) => {
      const next = !prev
      try {
        window.localStorage.setItem(`${storageKey}.collapsed`, String(next))
      } catch {
        // ignore storage errors (private mode, quota, etc.)
      }
      return next
    })
  }, [storageKey])

  const startResize = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      const startX = e.clientX
      const startWidth = storedWidthRef.current

      const previousCursor = document.body.style.cursor
      const previousUserSelect = document.body.style.userSelect
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'

      const handleMove = (moveEvent: MouseEvent) => {
        const delta = moveEvent.clientX - startX
        const next = Math.min(maxWidth, Math.max(minWidth, startWidth + delta))
        setStoredWidth(next)
      }

      const handleUp = () => {
        window.removeEventListener('mousemove', handleMove)
        window.removeEventListener('mouseup', handleUp)
        document.body.style.cursor = previousCursor
        document.body.style.userSelect = previousUserSelect
        try {
          window.localStorage.setItem(`${storageKey}.width`, String(storedWidthRef.current))
        } catch {
          // ignore storage errors
        }
      }

      window.addEventListener('mousemove', handleMove)
      window.addEventListener('mouseup', handleUp)
    },
    [maxWidth, minWidth, storageKey],
  )

  const width = isCollapsed ? minWidth : storedWidth

  return { width, isCollapsed, toggleCollapsed, startResize }
}
