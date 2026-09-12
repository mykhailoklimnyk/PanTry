/**
 * Чим показаний кошик розійшовся з екраном — і що з цим можна зробити (#86).
 *
 * Живий тест 20.08: гість змінив налаштування при зібраному кошику і побачив
 * у стрічці чипс «правила змінились · перезібрати». Дефектів там три, і всі
 * про одне — розбіжність не називала себе і не лишала вибору:
 *
 * — чипс стверджував «правила», хоча застарілим кошик роблять ще межа,
 *   тиждень, спосіб отримання, вхід, модель, список і погоджені ланцюжки:
 *   гість читав твердження про те, чого не робив;
 * — дотик по ньому нічого не питав, а одразу запускав тридцятисекундний
 *   прогін з викликом моделі — і стоїть чипс у стрічці, яку тягнуть пальцем;
 * — відповіді «прибрати зміну і лишити кошик як є» не існувало взагалі, хоча
 *   вона законна рівно так само, як перезбірка.
 *
 * Тому підпис і перелік змін рахуються ТУТ, з одного знімка налаштувань.
 * Два обчислення «що змінилось» розійшлися б мовчки саме там, де їх ніхто
 * не звіряє: підпис казав би «застаріло», а перелік не мав би чого показати.
 */
import { plural, uahRound } from './format'
import { parseList } from './list'
import { BUILD_MODES } from './ui'
import type { BuildRequest, Exclusion } from './types'

/**
 * Знімок усього, від чого залежить ВІДПОВІДЬ агента.
 *
 * Тут лежить сирий стан, а не підпис: із цього ж об'єкта гість повертає
 * налаштування назад до тих, за якими кошик уже зібрано.
 */
export interface Settings {
  rules: Exclusion[]
  budget: number
  mode: BuildRequest['mode']
  /** Скільки людей на подію; null — приводу немає, число не має сенсу. */
  people: number | null
  delivery: string
  /** Сирий текст списку: гість редагує саме його, підпис бере розібраний. */
  list: string
  model: string
  autoSwap: boolean
  source: BuildRequest['source']
}


/** Людські назви для id, які знає лише застосунок: способи і моделі. */
export interface Naming {
  delivery: (id: string) => string
  model: (id: string) => string
}

const SOURCES: Record<string, string> = {
  list: 'список і потреби тижня',
  cart: 'кошик акаунта',
}

const INTENTS = { one: 'позиція', few: 'позиції', many: 'позицій' }

function activeRules(settings: Settings): string[] {
  return settings.rules
    .filter((rule) => rule.active)
    .map((rule) => rule.label)
    .sort()
}

function modeName(id: string): string {
  return BUILD_MODES.find((mode) => mode.id === id)?.label ?? id
}

/** Підпис прогону: рівний — кошик відповідає екрану, різний — ні. */
export function signature(settings: Settings): string {
  return [
    activeRules(settings).join('|'),
    settings.budget,
    settings.mode,
    settings.delivery,
    parseList(settings.list).join('|'),
    settings.people ?? '',
    settings.model,
    settings.autoSwap ? 'auto' : '',
    settings.source,
  ].join('#')
}

/**
 * Що саме змінилось після збірки — словами гостя, а не підписом.
 *
 * Кожна складова підпису має тут свою гілку: розбіжність, якої перелік не
 * вміє назвати, лишила б вікно з двома кнопками і порожнім місцем над ними.
 */
export function changes(built: Settings, now: Settings, name: Naming): string[] {
  const was = activeRules(built)
  const has = activeRules(now)
  const out: string[] = []

  for (const label of has.filter((rule) => !was.includes(rule))) {
    out.push(`додано правило «${label}»`)
  }
  for (const label of was.filter((rule) => !has.includes(rule))) {
    out.push(`знято правило «${label}»`)
  }
  if (built.budget !== now.budget) {
    out.push(`межа: ${uahRound(built.budget)} → ${uahRound(now.budget)}`)
  }
  if (built.mode !== now.mode) {
    out.push(`режим: ${modeName(built.mode)} → ${modeName(now.mode)}`)
  }
  if (built.people !== null && now.people !== null && built.people !== now.people) {
    out.push(`гостей: ${built.people} → ${now.people}`)
  }
  if (built.delivery !== now.delivery) {
    out.push(`отримання: ${name.delivery(built.delivery)} → ${name.delivery(now.delivery)}`)
  }

  const wasList = parseList(built.list)
  const hasList = parseList(now.list)
  if (wasList.join('|') !== hasList.join('|')) {
    out.push(
      wasList.length === hasList.length
        ? 'список правлений'
        : `список: ${plural(wasList.length, INTENTS)} → ${plural(hasList.length, INTENTS)}`,
    )
  }
  if (built.source !== now.source) {
    out.push(`вхід: ${SOURCES[built.source] ?? built.source} → ${SOURCES[now.source] ?? now.source}`)
  }
  if (built.model !== now.model) {
    out.push(`модель: ${name.model(built.model)} → ${name.model(now.model)}`)
  }
  if (built.autoSwap !== now.autoSwap) {
    out.push(now.autoSwap ? 'авто-заміна увімкнена' : 'авто-заміна вимкнена')
  }
  return out
}

/**
 * Підпис чипса в стрічці: він мусить казати, ЩО саме розійшлось.
 *
 * Одна зміна називається повністю, кілька — числом: чипс стоїть у стрічці,
 * яку гортають убік, і три фрази підряд там просто не прочитають.
 */
export function staleLabel(list: string[]): string {
  if (list.length === 0) return 'кошик застарів · що робити?'
  if (list.length === 1) return `${list[0]} · що робити?`
  return `${plural(list.length, { one: 'зміна', few: 'зміни', many: 'змін' })} після збірки · що робити?`
}
