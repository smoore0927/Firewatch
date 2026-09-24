import { describe, expect, it } from 'vitest'
import { scoreLabel } from '@/types'
import { scoreToBadgeVariant } from '@/components/ui/badge'

// Same edge table as the backend's tests/test_severity.py: scoreLabel mirrors
// app/core/severity.py, so a cut-off changed on one side must fail here too.
const EDGES: [number, string][] = [
  [1, 'Low'],
  [5, 'Low'],
  [6, 'Medium'],
  [12, 'Medium'],
  [13, 'High'],
  [20, 'High'],
  [21, 'Critical'],
  [25, 'Critical'],
]

describe('severity cut-offs', () => {
  it.each(EDGES)('labels score %i as %s', (score, label) => {
    expect(scoreLabel(score)).toBe(label)
  })

  it('derives badge variants from the same cut-offs', () => {
    for (let score = 1; score <= 25; score++) {
      expect(scoreToBadgeVariant(score)).toBe(scoreLabel(score).toLowerCase())
    }
  })
})
