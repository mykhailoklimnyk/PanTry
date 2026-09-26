import type { CartLine, OrderFeedback } from './types'

export function collectorActs(feedback: OrderFeedback): boolean | null {
  if (feedback.changes === null) return null
  return feedback.changes !== 'disapprovedChanges'
}

export function swapsToReview(lines: CartLine[], feedback: OrderFeedback): boolean {
  const conflict =
    collectorActs(feedback) === false && lines.some((line) => line.mandate !== null)
  return (
    conflict ||
    lines.some((line) => line.atRisk && line.chain.length > 0) ||
    heldByFork(lines).length > 0
  )
}

export function heldByFork(lines: CartLine[]): CartLine[] {
  return lines.filter((line) => line.swapFork !== null)
}
