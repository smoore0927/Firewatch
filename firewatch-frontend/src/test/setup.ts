// Global setup for vitest. Loaded once via setupFiles in vitest.config.ts.
// - Imports jest-dom matchers so toBeInTheDocument / toHaveClass etc. are available.
// - Cleans up the rendered DOM between tests to prevent state bleed.
import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
})
