import { plural, uahRound } from './format'
import { parseList } from './list'
import { BUILD_MODES } from './ui'
import type { BuildRequest, Exclusion } from './types'

export interface Settings {
  rules: Exclusion[]
  budget: number
  mode: BuildRequest['mode']
  people: number | null
  delivery: string
  list: string
  model: string
  autoSwap: boolean
  source: BuildRequest['source']
}


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

export function staleLabel(list: string[]): string {
  if (list.length === 0) return 'кошик застарів · що робити?'
  if (list.length === 1) return `${list[0]} · що робити?`
  return `${plural(list.length, { one: 'зміна', few: 'зміни', many: 'змін' })} після збірки · що робити?`
}
