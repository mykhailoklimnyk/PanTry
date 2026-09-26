
import { plural, uahRound } from './format'
import type { BuildRequest, PantryItem } from './types'

export interface Thought {
  id: string
  text: string
  detail?: string
}


const KINDS = { one: 'вид', few: 'види', many: 'видів' }
const INTENTS = { one: 'намір', few: 'наміри', many: 'намірів' }
const PURCHASES = { one: 'покупка', few: 'покупки', many: 'покупок' }

interface Aisle {
  title: string
  kinds: number
  buys: number
}

function byAisle(pantry: PantryItem[]): Aisle[] {
  const seen = new Map<string, Aisle>()
  for (const item of pantry) {
    if (!item.aisle) continue
    const aisle = seen.get(item.aisle) ?? { title: item.aisle, kinds: 0, buys: 0 }
    aisle.kinds += 1
    aisle.buys += item.parts.reduce((sum, part) => sum + part.receipts, 0)
    seen.set(item.aisle, aisle)
  }
  return [...seen.values()].sort((a, b) => b.buys - a.buys || b.kinds - a.kinds)
}

function byCycle(pantry: PantryItem[]): PantryItem[] {
  return pantry
    .filter((item) => item.cycleDays !== null && item.cycleDays > 0)
    .sort((a, b) => (a.cycleDays ?? 0) - (b.cycleDays ?? 0))
}

export function thoughtsFor(
  pantry: PantryItem[],
  request: BuildRequest,
  listMode: string,
): Thought[] {
  const deck: Thought[] = []
  const list = request.shoppingList ?? []

  if (list.length > 0) {
    deck.push({
      id: 'list',
      text: `Твій список — ${plural(list.length, INTENTS)}, шукаю кожен окремо`,
      detail: list.slice(0, 4).join(' · ') + (list.length > 4 ? ' …' : ''),
    })
  }

  deck.push(...homeThoughts(pantry, listMode))

  if (request.budget) {
    deck.push({
      id: 'budget',
      text: `Тримаю межу ${uahRound(Number(request.budget))}: не влізе все — зніму найлегше і скажу, що саме`,
    })
  }

  return deck
}

export function homeThoughts(
  pantry: PantryItem[],
  listMode: string,
  settled = true,
): Thought[] {
  const deck: Thought[] = []

  if (settled && pantry.length > 0) {
    const known = byCycle(pantry).length
    deck.push({
      id: 'kinds',
      text:
        known === pantry.length
          ? `Твоя комора — це ${plural(pantry.length, KINDS)}, і я знаю цикл кожного`
          : `Твоя комора — це ${plural(pantry.length, KINDS)}, цикл знаю у ${known}`,
    })
  }

  const out = pantry.filter((item) => item.runningOut)
  if (out.length > 0) {
    deck.push({
      id: 'out',
      text: `Уже закінчилось — ${plural(out.length, KINDS)}`,
      detail:
        out
          .slice(0, 3)
          .map((item) => item.label)
          .join(' · ') + ' — беру в кошик першою чергою',
    })
  }

  const aisles = byAisle(pantry)
  const biggest = aisles[0]
  if (biggest && biggest.buys > 0) {
    deck.push({
      id: 'aisle',
      text: `Найчастіше — відділ «${biggest.title}»: ${plural(biggest.buys, PURCHASES)} у ${plural(biggest.kinds, KINDS)}`,
      detail:
        aisles.length > 1
          ? `далі — ${aisles
              .slice(1, 3)
              .map((aisle) => `«${aisle.title}»`)
              .join(' і ')}`
          : undefined,
    })
  }


  const soon = pantry
    .filter((item) => !item.runningOut && item.daysLeft !== null && item.daysLeft > 0)
    .sort((a, b) => (a.daysLeft ?? 0) - (b.daysLeft ?? 0))[0]
  if (soon?.daysLeft && soon.aisle) {
    deck.push({
      id: 'soon',
      text: `Далі в черзі — щось із відділу «${soon.aisle}»: ще ~${soon.daysLeft} дн`,
    })
  }

  const brand = pantry.find((item) => item.usual !== null)
  if (brand?.usual) {
    deck.push({
      id: 'brand',
      text: `Під «${brand.label.toLowerCase()}» беру «${brand.usual.name}» — саме це ти й купуєш`,
      detail: brand.usual.share,
    })
  }

  const added = pantry.filter((item) => item.source === 'manual')
  if (added.length > 0) {
    deck.push({
      id: 'manual',
      text:
        listMode === 'manual'
          ? `Список ведеш ти — про ${plural(added.length, KINDS)} чеки мовчать, вірю на слово`
          : `Ти додав руками ${plural(added.length, KINDS)} — у чеках про це нічого, вірю на слово`,
    })
  }

  return deck
}
