
const MONEY = new Intl.NumberFormat('uk-UA', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const MONEY_ROUND = new Intl.NumberFormat('uk-UA', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

const AMOUNT = new Intl.NumberFormat('uk-UA', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
})

const NBSP = ' '

const TZ = 'Europe/Kyiv'

const TIME = new Intl.DateTimeFormat('uk-UA', {
  hour: '2-digit',
  minute: '2-digit',
  timeZone: TZ,
})
const WEEKDAY = new Intl.DateTimeFormat('uk-UA', { weekday: 'short', timeZone: TZ })
const DAY_MONTH = new Intl.DateTimeFormat('uk-UA', {
  day: 'numeric',
  month: 'long',
  timeZone: TZ,
})

/** «113,80 ₴» — ціни й суми рядків. */
export function uah(value: number): string {
  return `${MONEY.format(value)}${NBSP}₴`
}

/** «1 660 ₴» — велика сума в підсумку, де копійки лише шумлять. */
export function uahRound(value: number): string {
  return `${MONEY_ROUND.format(Math.round(value))}${NBSP}₴`
}

/** «2 шт», «1,2 кг» — кількість з одиницею з API. */
export function amount(value: number, unit: string): string {
  if (!unit) return AMOUNT.format(value)
  return `${AMOUNT.format(value)}${NBSP}${unit}`
}

/** «12,4 кг» */
export function kg(value: number): string {
  return `${AMOUNT.format(value)}${NBSP}кг`
}

/** «6,1 с» — тривалість прогону в шапці трейсу. */
export function seconds(ms: number): string {
  return `${AMOUNT.format(Math.round(ms / 100) / 10)}${NBSP}с`
}

/**
 * Тривалість КРОКУ трейсу.
 *
 * `null` — крок НІХТО не міряв, і так і сказано словами: числа тут немає, а
 * порожнє місце поруч із «169 мс» сусіда нерозрізненне зі зламаним показником.
 * До 02.09 незаміряний крок приїжджав нулем і малювався як «<1 мс» — власник
 * прочитав це як брехню, і був правий (#279).
 *
 * Нуль тепер означає рівно одне — ЗАМІРЯНИЙ нуль, тобто швидше за мілісекунду.
 */
export function stepTime(ms: number | null): string {
  if (ms === null) return 'не міряли'
  if (ms <= 0) return `<1${NBSP}мс`
  if (ms < 1000) return `${ms}${NBSP}мс`
  return seconds(ms)
}

/** «$0,04» — вартість прогону. Долар, бо так її виставляє Bedrock. */
export function usd(value: number): string {
  return `$${MONEY.format(value)}`
}

const MONEY_FINE = new Intl.NumberFormat('uk-UA', { maximumSignificantDigits: 2 })

/** «$0,04» для видимого і «$0,0009» для того, що інакше стало б нулем. */
export function usdFine(value: number): string {
  if (value > 0 && value < 0.01) return `$${MONEY_FINE.format(value)}`
  return usd(value)
}

/** «пт 11:00–13:00» — вікно доставки. */
export function slotLabel(slot: { start: string; end: string } | null): string | null {
  if (!slot) return null
  const start = new Date(slot.start)
  const end = new Date(slot.end)
  return `${WEEKDAY.format(start)}${NBSP}${TIME.format(start)}–${TIME.format(end)}`
}

/** «чт, 13 серпня» — дата під назвою в шапці. */
export function dayLabel(date: Date): string {
  return `${WEEKDAY.format(date)}, ${DAY_MONTH.format(date)}`
}

/**
 * Українська множина: 1 позиція · 2 позиції · 5 позицій.
 *
 * Через `Intl.PluralRules`, а не через власні `% 10` і `% 100`: правила мови
 * — це дані, а не арифметика, і писати їх руками тут немає жодної причини.
 */
const PLURAL = new Intl.PluralRules('uk-UA')

export function plural(count: number, forms: { one: string; few: string; many: string }): string {
  const rule = PLURAL.select(count)
  const word = rule === 'one' ? forms.one : rule === 'few' ? forms.few : forms.many
  return `${count}${NBSP}${word}`
}

/**
 * Перша частина пояснення — те, що влазить у рядок списку.
 * Решта живе у спливашці «i»: рядок не має рости від довгого тексту.
 */
export function shortWhy(explanation: string): string {
  return explanation.split(' · ')[0] ?? explanation
}

/**
 * Перша частина речення: сама причина, без поради і без чисел межі.
 *
 * Причина недобору стоїть у двох місцях -- коротко в плашці з сумою і
 * цілком у блоці добору (#206). Різати ТЕКСТ, а не писати другий: два
 * формулювання однієї причини розійшлись би першою ж правкою (#158).
 */
export function firstClause(note: string): string {
  const cut = note.split(' — ')[0] ?? note
  return cut.split('. ')[0] ?? cut
}
