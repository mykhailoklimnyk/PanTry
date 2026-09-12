
import type { PantryAdjustment, PantryItem } from './types'

export interface PantryEdit {
  action: PantryAdjustment['action']
  qty: number
  days: number
  /** Намір, який розділяють чи згортають назад (#335). Лише для `split`. */
  group?: string
  /**
   * Артикули, якими замінити цей вид (#332). Лише для `mandate`.
   *
   * Самі артикули, без назв: мандат читає людина біля полиці, і назва,
   * надіслана звідси, стала б нашою обіцянкою від імені гостя про товар,
   * якого він не називав (#128). Рядок мандата збирає сервер з його ж чеків.
   */
  chain?: string[]
}

/**
 * Скільки чекати, поки гість дотискає. Число з заміру, а не з голови: сам
 * запит коштує 3,7 с, тож пів секунди на екрані непомітні, а склеюють вони
 * рівно ту серію дотиків, з якої почалась скарга.
 */
export const SETTLE_MS = 500

/**
 * Порядок, у якому рядки стоять зараз. Знімається при ВІДКРИТТІ комори і
 * переживає всі правки цього візиту.
 */
export function order(items: PantryItem[]): string[] {
  return items.map((item) => item.id)
}

/**
 * Свіжа комора, розкладена в порядку, який гість уже бачить.
 *
 * Рядок, якого в тому порядку не було, іде ПОПЕРЕДУ решти: це або щойно
 * дописаний вид, або той, що з'явився в чеках, — і загубити його серед
 * сорока рядків гірше, ніж поставити зависоко (#85).
 */
export function keepOrder(items: PantryItem[], seen: string[]): PantryItem[] {
  if (seen.length === 0) return items
  const place = new Map(seen.map((id, index) => [id, index]))
  const known = items.filter((item) => place.has(item.id))
  const fresh = items.filter((item) => !place.has(item.id))
  known.sort((a, b) => (place.get(a.id) ?? 0) - (place.get(b.id) ?? 0))
  return [...fresh, ...known]
}

/**
 * Кількість, яку гість щойно назвав, — на екран, не чекаючи сервера.
 *
 * Решта рядка не чіпається навмисно: смугу і «ще ~N дн» рахує сервер з
 * циклу, і домалювати їх тут означало б завести другий дім тому самому
 * правилу (`core/leftover.py`).
 */
export function withQty(items: PantryItem[], id: string, qty: number): PantryItem[] {
  return items.map((item) => (item.id === id ? { ...item, qty } : item))
}

/** Наступна кількість після дотику по «+» чи «-». Не нижче нуля. */
export function stepped(qty: number, delta: number, step: number): number {
  return Math.max(0, Math.round((qty + delta * step) * 100) / 100)
}

/**
 * Заголовок наміру над своїми рядками -- один вид, один рядок на екрані (#335).
 *
 * Сервер уже поставив членів групи поруч і зняв групу там, де гість її
 * РОЗДІЛИВ, тож тут лишається рівно малювання. Але умова «двоє поруч»
 * перевіряється ще раз, і не для страховки: пошук по коморі ховає рядки, і
 * заголовок над однією позицією, що лишилась від групи з п'яти, стверджував
 * би про неї те, чого немає. Група, яка не склалась, не має права виглядати
 * як група.
 *
 * `out` рахується тут, а не приїжджає числом: це підрахунок рівно тих
 * рядків, які екран зараз малює, а не тих, які сервер колись бачив, -- і
 * розійтись їм так нема з чим.
 */
export interface Shelf {
  item: PantryItem
  /** Намір, якщо цим рядком група ПОЧИНАЄТЬСЯ. Інакше порожньо. */
  head: string | null
  /** Скільки рядків під заголовком. Має сенс лише разом з `head`. */
  size: number
  /** Скільки з них закінчується: згортання не має права поховати те,
      заради чого екран існує (#107). */
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
