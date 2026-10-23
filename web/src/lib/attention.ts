import type { CartLine } from './types'

export const asksWord = (line: Pick<CartLine, 'atRisk' | 'needsApproval' | 'decided'>): boolean =>
  line.needsApproval || (line.atRisk && !line.decided)
