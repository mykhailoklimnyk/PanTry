
import type { Exclusion } from './types'

const KEY = 'komora:rules'

export interface Cached {
  id: string
  label: string
  active: boolean
  /** Правка ще не підтверджена сервером. Відсутнє поле — спадщина, теж «так». */
  pending?: boolean
}

/**
 * Слова гостя, приведені до вигляду, у якому їх можна порівнювати. Дзеркало
 * `core/rules.clean`: тільки краї й повторні пробіли — решту тексту читає
 * агент, і міняти його ми права не маємо.
 */
export function clean(label: string): string {
  return label.trim().replace(/\s+/g, ' ')
}

/** Ключ дублікатів. Дзеркало `core/rules.key`: те саме плюс регістр. */
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

/** Що з кешу ще не доїхало до сервера. */
function unsynced(list: Cached[]): Cached[] {
  return list.filter((row) => row.pending !== false)
}

/**
 * Правила з кешу, яких сервер не знає, — саме вони їдуть у першу
 * синхронізацію. Порівняння за СЛОВАМИ, не за id: id локального запису
 * тимчасовий, а серверний — відбиток тексту, і зійтись вони не можуть.
 */
export function missing(server: Exclusion[], list: Cached[]): Cached[] {
  const known = new Set(server.map((rule) => labelKey(rule.label)))
  return unsynced(list).filter((row) => !known.has(labelKey(row.label)))
}

/** Тимчасовий id до відповіді сервера: справжній — відбиток слів, і його рахує сервер. */
export function localId(label: string): string {
  return `local:${labelKey(label)}`
}

export function remember(rules: Cached[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(rules))
  } catch {
  }
}

/** Підтверджене сервером: те, що лежить у базі, і нічого понад це. */
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
