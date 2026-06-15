import { useEffect, useRef } from 'react'

/**
 * Calls `handler` when Escape is pressed, while `active` is true.
 *
 * Replaces the identical window keydown effect that was hand-written in every
 * dialog. The handler is kept in a ref so passing an inline arrow does not
 * re-bind the listener on every render — it only re-binds when `active` flips.
 */
export function useEscapeKey(handler: () => void, active = true): void {
  const handlerRef = useRef(handler)
  useEffect(() => {
    handlerRef.current = handler
  })

  useEffect(() => {
    if (!active) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') handlerRef.current()
    }
    globalThis.addEventListener('keydown', onKey)
    return () => globalThis.removeEventListener('keydown', onKey)
  }, [active])
}
