
import type { PantryAdjustment, PantryItem } from './types'

export interface PantryEdit {
  action: PantryAdjustment['action']
  qty: number
  days: number
  group?: string
  chain?: string[]
}

export const SETTLE_MS = 500

export function order(items: PantryItem[]): string[] {
  return items.map((item) => item.id)
}

export function keepOrder(items: PantryItem[], seen: string[]): PantryItem[] {
  if (seen.length === 0) return items
  const place = new Map(seen.map((id, index) => [id, index]))
  const known = items.filter((item) => place.has(item.id))
  const fresh = items.filter((item) => !place.has(item.id))
  known.sort((a, b) => (place.get(a.id) ?? 0) - (place.get(b.id) ?? 0))
  return [...fresh, ...known]
}

export function withQty(items: PantryItem[], id: string, qty: number): PantryItem[] {
  return items.map((item) => (item.id === id ? { ...item, qty } : item))
}

export function stepped(qty: number, delta: number, step: number): number {
  return Math.max(0, Math.round((qty + delta * step) * 100) / 100)
}

export interface Shelf {
  item: PantryItem
  head: string | null
  size: number
  out: number
}

export function shelves(items: PantryItem[]): Shelf[] {
  const runs: PantryItem[][] = []
  for (const item of items) {
    const last = runs.at(-1)
    const head = last?.[0]
    if (last && head && item.group !== null && head.group === item.group) last.push(item)
    else runs.push([item])
  }
  return runs.flatMap((run) =>
    run.map((item, index) => ({
      item,
      head: index === 0 && run.length > 1 && item.group !== null ? item.group : null,
      size: run.length,
      out: run.filter((row) => row.runningOut).length,
    })),
  )
}
