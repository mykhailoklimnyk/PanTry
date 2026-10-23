
import { amount, plural, uahRound, usdFine } from './format'
import type {
  Bar,
  BuildRequest,
  CartLine,
  DrinkKind,
  Pantry,
  Toll,
} from './types'

export const DEBUG_KEY = 'komora:debug'

export function brandHtml(text: string): string {
  const safe = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return safe.split('ПанTry').join('<b>ПанTry</b>')
}

export const SPEECH_DIAG_KEY = 'komora:speech-diag'

export function speechDiagEnabled(): boolean {
  try {
    return localStorage.getItem(SPEECH_DIAG_KEY) === '1'
  } catch {
    return false
  }
}

export function debugEnabled(): boolean {
  try {
    return localStorage.getItem(DEBUG_KEY) === '1'
  } catch {
    return false
  }
}

export function isBuying(line: CartLine): boolean {
  return line.reason !== 'at_home'
}

export const DEFAULT_DELIVERY = 'DeliveryHome'

export const DELIVERY_SKELETON = [64, 88, 72, 96, 80, 68]

export const RULE_SUGGESTIONS = [
  'без свинини',
  'без глютену',
  'менше цукру',
  'тільки українське',
  'нічого в склі',
]

export const FILTER_FROM = 12

export const PANTRY_SUGGESTIONS = ['гречка', 'сіль', 'мед', 'оцет']

export const PANTRY_CHIPS = 4

export function plainKind(text: string): string {
  return text.toLowerCase().replaceAll('\u2019', "'").trim()
}

export type AddHints = {
  chips: string[]
  note: string
}

export function addHints(pool: string[], untracked: string[], typed: string): AddHints {
  const needle = plainKind(typed)
  if (needle !== '') {
    const hit = pool.filter((kind) => plainKind(kind).includes(needle))
    if (hit.length > 0) {
      return {
        chips: hit.slice(0, PANTRY_CHIPS),
        note: 'таке в тебе вже є — візьми це слово, щоб у коморі не завелось два рядки одного виду',
      }
    }
    return { chips: [], note: 'серед твоїх видів такого ще немає — додам новим' }
  }
  if (untracked.length > 0) {
    return {
      chips: untracked.slice(0, PANTRY_CHIPS),
      note: 'з твоїх покупок — комора їх ще не веде',
    }
  }
  return {
    chips: PANTRY_SUGGESTIONS,
    note: 'своїх видів поки не видно — ось приклади ФОРМИ: вид, а не марка',
  }
}

export function pantryStep(unit: string): number {
  return unit === 'кг' || unit === 'л' ? 0.1 : 1
}

const STOCK_AHEAD = [2, 3, 4]

export function boughtChoices(usual: number, step: number): number[] {
  const values = new Set<number>()
  const onStep = (value: number) => Math.round(Math.round(value / step) * step * 100) / 100
  for (const share of [0.25, 0.5, 0.75]) {
    const value = onStep(usual * share)
    if (value > 0 && value < usual) values.add(value)
  }
  for (const times of STOCK_AHEAD) {
    const value = onStep(usual * times)
    if (value > usual) values.add(value)
  }
  return [...values].sort((a, b) => a - b)
}

export function cycleAsk(usualQty: number | null, unit: string): string {
  if (usualQty === null) return 'На скільки тобі цього вистачає?'
  return `На скільки вистачає ${amount(usualQty, unit)}?`
}

export function stockDays(
  qty: number,
  usual: number,
  cycleDays: number | null,
  said: boolean,
): number | null {
  if (!said || cycleDays === null || usual <= 0) return null
  return Math.max(1, Math.round((cycleDays * qty) / usual))
}

export const KEEPS_LIMIT: Record<string, number> = {
  дні: 7,
  тижні: 30,
  місяці: 365,
}

export const ASK_AT_ONCE = 3

export function cycleChoicesFor(keeps: string | null): { days: number; label: string }[] {
  const limit = keeps === null ? null : KEEPS_LIMIT[keeps]
  if (limit === undefined || limit === null) return CYCLE_CHOICES
  const fits = CYCLE_CHOICES.filter((choice) => choice.days <= limit)
  return fits.length > 0 ? fits : CYCLE_CHOICES
}

export const CYCLE_CHOICES: { days: number; label: string }[] = [
  { days: 1, label: 'на день' },
  { days: 2, label: 'на 2 дні' },
  { days: 3, label: 'на 3 дні' },
  { days: 7, label: 'на тиждень' },
  { days: 14, label: 'на 2 тижні' },
  { days: 30, label: 'на місяць' },
]

export const BAR_GROUPS: { kind: DrinkKind; label: string; note: string }[] = [
  { kind: 'strong', label: 'міцний', note: 'береш рідко і під привід' },
  { kind: 'wine', label: 'вино', note: 'найчастіше — до вечері з гостями' },
  { kind: 'light', label: 'слабкий', note: 'пиво і сидр' },
]

export interface Phase {
  id: string
  label: string
  call: string
  after: number
}

export const BUILD_PHASES: [Phase, ...Phase[]] = [
  { id: 'place', label: 'Дивлюсь, у якому ти магазині', call: 'get_available_delivery_types', after: 0 },
  { id: 'slots', label: 'Беру найближче вікно доставки', call: 'get_time_slots', after: 900 },
  { id: 'history', label: 'Читаю твої чеки — усю історію', call: 'get_my_offline_orders', after: 1100 },
  { id: 'kinds', label: 'Звужую наміри до видів деревом категорій', call: 'get_products', after: 3300 },
  { id: 'shelf', label: 'Дивлюсь, що є на полиці саме зараз', call: 'find_products_batch', after: 5500 },
  { id: 'agent', label: 'Обираю під кожен намір конкретний товар', call: 'модель', after: 6800 },
]



export const PANTRY_PHASES: [Phase, ...Phase[]] = [
  {
    id: 'place',
    label: 'Дивлюсь, у якому ти магазині',
    call: 'get_my_delivery_addresses',
    after: 0,
  },
  {
    id: 'history',
    label: 'Читаю чеки — усю історію, не три місяці',
    call: 'get_my_offline_orders',
    after: 1600,
  },
  {
    id: 'kinds',
    label: 'Називаю види: «Напій Geo» — це вода газована',
    call: 'модель',
    after: 4200,
  },
]

export const BUILD_MODES: { id: BuildRequest['mode']; label: string; note: string }[] = [
  { id: 'week', label: 'на тиждень', note: 'Комора, цикли й ціль суми.' },
  { id: 'event', label: 'подія', note: "Стіл: вино, закуски, м'ясо, сир." },
  { id: 'list', label: 'зі списку', note: 'Тільки те, що ти записав.' },
]

export const BUDGET_PRESETS = [1200, 1700, 2300, 3000]

export const BAND_TOLERANCE = 0.1

export function targetChip(budget: number, source: Omit<Pantry, 'items'> | null): string {
  const goal = `зібрати приблизно на ${uahRound(budget)}`
  if (source === null) return goal
  if (source.targetPool === 0) {
    return source.receipts === 0 && source.orders === 0
      ? 'нема з чого добирати: покупок ще не видно'
      : `нема з чого добирати: бачу ${purchasesPhrase(source)}`
  }
  const reach = source.targetEstimate
  if (reach === null || reach >= budget * (1 - BAND_TOLERANCE)) return goal
  return `${goal} · з твоїх покупок ~${uahRound(reach)}`
}

export const NO_PHOTO = {
  line: '🛒',
  pantry: '📦',
  drink: '🍾',
}

export function sourcesPhrase(source: { receipts: number; orders: number }): string {
  return (
    plural(source.receipts, { one: 'чек', few: 'чеки', many: 'чеків' }) +
    ', ' +
    plural(source.orders, { one: 'замовлення', few: 'замовлення', many: 'замовлень' })
  )
}

function purchasesPhrase(source: { receipts: number; orders: number }): string {
  const paper = plural(source.receipts, { one: 'чек', few: 'чеки', many: 'чеків' })
  const web = plural(source.orders, { one: 'замовлення', few: 'замовлення', many: 'замовлень' })
  if (source.receipts === 0) return web
  if (source.orders === 0) return paper
  return `${paper} і ${web}`
}

function bySelfEmptyNote(source: Omit<Pantry, 'items'>): string {
  if (source.receipts === 0 && source.orders === 0) {
    return (
      'Покупок у «Сільпо» ще не видно взагалі — «Скласти з покупок» поки ' +
      'нічого не принесе. Додай перший вид сам.'
    )
  }
  if (source.kinds === 0) {
    return (
      'Покупки бачу, але жоден вид ще не повторився стільки разів, щоб я ' +
      'був певен, що ти береш його регулярно — «Скласти з покупок» поки ' +
      'нічого не принесе. Додай вид сам.'
    )
  }
  if (source.unlisted > 0) {
    return (
      'Список ти ведеш сам, і зараз він порожній. У покупках є ще ' +
      `${plural(source.unlisted, { one: 'вид', few: 'види', many: 'видів' })} — ` +
      'склади список з них або додай вид сам.'
    )
  }
  return 'Нового виду з покупок для списку зараз немає — або ти сховав усі. Додай вид сам.'
}

export function pantryEmptyNote(source: Omit<Pantry, 'items'>): string {
  if (source.source === 'manual') return bySelfEmptyNote(source)
  if (source.receipts === 0 && source.orders === 0) {
    return (
      'Комора наповнюється сама — з твоїх покупок у «Сільпо». Поки їх не видно: ' +
      'купуй як завжди, з карткою, і за кілька разів я знатиму, що в тебе вдома ' +
      'і коли воно закінчується.'
    )
  }
  if (source.kinds === 0) {
    return (
      `Бачу ${purchasesPhrase(source)}, але «Сільпо» не показує, що в них було — ` +
      'старі замовлення приходять без переліку товарів. Рахувати поки нема з чого: ' +
      'комора почне заповнюватись з наступних покупок.'
    )
  }
  return (
    `Перші покупки вже бачу: ${purchasesPhrase(source)}, ` +
    `${plural(source.kinds, { one: 'вид', few: 'види', many: 'видів' })}. ` +
    `Щоб порахувати, як швидко щось закінчується, треба побачити вид у ${source.trackedFrom} ` +
    'покупках у різні дні — далі комора почне заповнюватись сама.'
  )
}

export function barEmptyNote(source: Omit<Bar, 'items'>): string {
  if (source.receipts === 0 && source.orders === 0) {
    return (
      `Бар — це пам'ять про твої покупки в «Сільпо». Поки їх не видно: ` +
      `купуй як завжди, з карткою, і я запам'ятаю, що ти береш і як часто.`
    )
  }
  if (source.named === 0) {
    return (
      `Покупки бачу (${purchasesPhrase(source)}), ` +
      'а от що з них напій — вирішує агент, і зараз він не відповів. ' +
      'Це не «алкоголю немає», це «ще не порахував» — зайди трохи згодом.'
    )
  }
  if (source.dropped > 0) {
    return (
      `Напої в чеках є, але показати їх нема з чим: ` +
      `${plural(source.dropped, { one: 'вид', few: 'види', many: 'видів' })} ` +
      'без ціни або без дати покупки. Рядок бару обіцяє збирачу вилку цін, ' +
      'а без числа обіцянки немає — тому вид і не стоїть.'
    )
  }
  return (
    `Серед звичного напоїв поки немає: ${purchasesPhrase(source)}, ` +
    `${plural(source.kinds, { one: 'вид', few: 'види', many: 'видів' })}. ` +
    `Вид потрапляє в бар з ${source.trackedFrom}-ї покупки — одна пляшка це ще не звичка.`
  )
}

export function barDroppedNote(source: Omit<Bar, 'items'>): string | null {
  if (source.dropped === 0) return null
  return (
    `Ще ${plural(source.dropped, { one: 'вид', few: 'види', many: 'видів' })} ` +
    'не показано: у чеках немає ні ціни, ні дати покупки, а вилку цін збирачу ' +
    'без них не пообіцяти.'
  )
}

export function tollNote(toll: Toll | null, label = 'цей вхід'): string | null {
  if (toll === null || toll.runs === 0) return null
  const runs = plural(toll.runs, { one: 'прогін', few: 'прогони', many: 'прогонів' })
  const money = toll.usd === null ? 'ціни моделі не знаємо' : usdFine(toll.usd)
  const gap =
    toll.usd !== null && toll.unpriced > 0
      ? ` (без ${plural(toll.unpriced, { one: 'прогону', few: 'прогонів', many: 'прогонів' })} без прайсу)`
      : ''
  const whose =
    toll.guestUsd === null
      ? ''
      : toll.guestUsd === toll.usd
        ? ' · ключем гостя, поза добовою стелею'
        : ` · з них ${usdFine(toll.guestUsd)} ключем гостя, поза добовою стелею`
  return `${label}: ${runs} · ${money}${gap}${whose} · ${toll.tokensIn} → ${toll.tokensOut} ток.`
}


export function tollSince(now: Toll | null, base: Toll | null): Toll | null {
  if (now === null) return null
  const was = base ?? { runs: 0, usd: 0, unpriced: 0, tokensIn: 0, tokensOut: 0, guestUsd: 0 }
  const runs = now.runs - was.runs
  if (runs <= 0) return null
  const unpriced = now.unpriced - was.unpriced
  return {
    runs,
    usd: now.usd === null ? null : now.usd - (was.usd ?? 0),
    unpriced,
    tokensIn: now.tokensIn - was.tokensIn,
    tokensOut: now.tokensOut - was.tokensOut,
    guestUsd: now.guestUsd === null ? null : now.guestUsd - (was.guestUsd ?? 0),
  }
}