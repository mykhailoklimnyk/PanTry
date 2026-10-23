export type Screen =
  | 'start'
  | 'running'
  | 'cart'
  | 'trace'
  | 'swaps'
  | 'pantry'
  | 'bar'
  | 'order'
  | 'connect'
  | DocId

export type DocId = 'quality' | 'stack' | 'ideas'

const DOC_IDS: DocId[] = ['quality', 'stack', 'ideas']

export function isDoc(screen: Screen): screen is DocId {
  return (DOC_IDS as string[]).includes(screen)
}

export const TABS: Screen[] = ['cart', 'pantry', 'bar']

const ROOTS: Screen[] = ['start', 'cart']

const MAX_TRAIL = 8

export function pushed(trail: Screen[], from: Screen, to: Screen): Screen[] {
  if (from === to || to === 'running') return trail
  if (ROOTS.includes(to)) return []
  if (from === 'running') return trail
  if (TABS.includes(from) && TABS.includes(to) && from !== 'cart') return trail
  return [...trail, from].slice(-MAX_TRAIL)
}

export function popped(trail: Screen[]): { to: Screen; trail: Screen[] } {
  const to = trail.at(-1) ?? 'start'
  return { to, trail: trail.slice(0, -1) }
}

export function backLabel(to: Screen): string {
  if (to === 'cart') return 'До кошика'
  if (to === 'pantry') return 'До комори'
  if (to === 'bar') return 'До бару'
  if (to === 'order') return 'До замовлення'
  if (to === 'connect') return 'До акаунта'
  return 'До покупок'
}

export function inTabs(screen: Screen, trail: Screen[]): boolean {
  return screen === 'cart' || (TABS.includes(screen) && trail.at(-1) === 'cart')
}
