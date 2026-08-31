import { describe, expect, it } from 'vitest'
import { pinOutcomeRow, resultShareText } from './resultShare'

describe('result sharing', () => {
  it('renders solved Pins in canonical order without exposing answers', () => {
    expect(pinOutcomeRow(5, [3, 1, 2])).toBe('❌ 2️⃣ 3️⃣ 4️⃣ ❌')
  })

  it('builds a compact result without adding the share URL to native text', () => {
    expect(resultShareText({
      productName: 'Hamburg Whereabouts',
      challengeLabel: 'Daily Challenge · August 28, 2026',
      score: '3/5 Pins · 8/10 Guesses',
      outcomeRow: '❌ 2️⃣ 3️⃣ 4️⃣ ❌',
    })).toBe([
      'Hamburg Whereabouts',
      'Daily Challenge · August 28, 2026',
      '3/5 Pins · 8/10 Guesses',
      '❌ 2️⃣ 3️⃣ 4️⃣ ❌',
    ].join('\n'))
  })
})
