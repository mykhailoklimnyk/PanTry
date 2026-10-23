
import type { Exclusion } from './types'

const KEY = 'komora:rules'

export interface Cached {
  id: string
  label: string
  active: boolean
  pending?: boolean
}

export function clean(label: string): string {
  return label.trim().replace(/\s+/g, ' ')
}

export function labelKey(label: string): string {
  return clean(label).toLowerCase()
}

export function cached(): Cached[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '[]') as unknown
    if (!Array.isArray(raw)) return []
    return raw
      .filter((row): row is Cached => typeof row?.label === 'string' && row.label.trim() !== '')
      .map((row) => ({
        id: typeof row.id === 'string' ? row.id : localId(row.label),
        label: row.label,
        active: row.active !== false,
        pending: row.pending !== false,
      }))
  } catch {
    return []
  }
}

function unsynced(list: Cached[]): Cached[] {
  return list.filter((row) => row.pending !== false)
}

export function missing(server: Exclusion[], list: Cached[]): Cached[] {
  const known = new Set(server.map((rule) => labelKey(rule.label)))
  return unsynced(list).filter((row) => !known.has(labelKey(row.label)))
}

export function localId(label: string): string {
  return `local:${labelKey(label)}`
}

export function remember(rules: Cached[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(rules))
  } catch {
  }
}

export function confirmed(own: Exclusion[]): Cached[] {
  return own.map((rule) => ({
    id: rule.id,
    label: rule.label,
    active: rule.active,
    pending: false,
  }))
}

export function forget(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
  }
}
