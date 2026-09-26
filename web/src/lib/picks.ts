import type { CartLine } from './types'

export function hasPick(line: CartLine): boolean {
  return line.consideredTotal > 0
}

export function pickId(externalProductId: string): string {
  return `pick-${externalProductId}`
}

export function pickLabel(line: CartLine): string {
  return line.consideredTotal > 1 ? `обрано з ${line.consideredTotal}` : 'вибору не було'
}
