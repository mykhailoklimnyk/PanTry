
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

export function uah(value: number): string {
  return `${MONEY.format(value)}${NBSP}₴`
}

export function uahRound(value: number): string {
  return `${MONEY_ROUND.format(Math.round(value))}${NBSP}₴`
}

export function amount(value: number, unit: string): string {
  if (!unit) return AMOUNT.format(value)
  return `${AMOUNT.format(value)}${NBSP}${unit}`
}

export function kg(value: number): string {
  return `${AMOUNT.format(value)}${NBSP}кг`
}

export function seconds(ms: number): string {
  return `${AMOUNT.format(Math.round(ms / 100) / 10)}${NBSP}с`
}

export function stepTime(ms: number | null): string {
  if (ms === null) return 'не міряли'
  if (ms <= 0) return `<1${NBSP}мс`
  if (ms < 1000) return `${ms}${NBSP}мс`
  return seconds(ms)
}

export function usd(value: number): string {
  return `$${MONEY.format(value)}`
}

const MONEY_FINE = new Intl.NumberFormat('uk-UA', { maximumSignificantDigits: 2 })

export function usdFine(value: number): string {
  if (value > 0 && value < 0.01) return `$${MONEY_FINE.format(value)}`
  return usd(value)
}

export function slotLabel(slot: { start: string; end: string } | null): string | null {
  if (!slot) return null
  const start = new Date(slot.start)
  const end = new Date(slot.end)
  return `${WEEKDAY.format(start)}${NBSP}${TIME.format(start)}–${TIME.format(end)}`
}

export function dayLabel(date: Date): string {
  return `${WEEKDAY.format(date)}, ${DAY_MONTH.format(date)}`
}

const PLURAL = new Intl.PluralRules('uk-UA')

export function plural(count: number, forms: { one: string; few: string; many: string }): string {
  const rule = PLURAL.select(count)
  const word = rule === 'one' ? forms.one : rule === 'few' ? forms.few : forms.many
  return `${count}${NBSP}${word}`
}

export function shortWhy(explanation: string): string {
  return explanation.split(' · ')[0] ?? explanation
}

export function firstClause(note: string): string {
  const cut = note.split(' — ')[0] ?? note
  return cut.split('. ')[0] ?? cut
}
