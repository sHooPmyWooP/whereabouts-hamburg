export function pinOutcomeRow(pinCount: number, solvedPinIndices: number[]) {
  const solved = new Set(solvedPinIndices)
  return Array.from({ length: pinCount }, (_, index) => (
    solved.has(index) ? `${index + 1}\uFE0F\u20E3` : '❌'
  )).join(' ')
}

export function resultShareText(parts: {
  productName: string
  challengeLabel: string
  score: string
  outcomeRow: string
}) {
  return [parts.productName, parts.challengeLabel, parts.score, parts.outcomeRow].join('\n')
}
