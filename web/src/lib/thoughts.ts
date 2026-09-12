
import { plural, uahRound } from './format'
import type { BuildRequest, PantryItem } from './types'

/** Одна репліка. `detail` — дрібним поруч, коли є чим підперти число. */
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

/**
 * Відділи комори, від найгучнішого: скільки видів і скільки покупок у чеках.
 *
 * Вісь тут ЧУЖА і вже оплачена -- корінь дерева «Сільпо» (#337), той самий,
 * що малює рейку над списком. Свого переліку категорій у коді немає з тієї ж
 * причини, з якої немає переліку марок (#108): він протух би за місяць і
 * належав би ОДНОМУ акаунту.
 */
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

/**
 * Колода реплік під цей прогін. Порядок сталий: спершу про список гостя,
 * далі про його дім — від найгучнішого факту до найтихішого.
 *
 * Порожня комора (новий гість) дає порожню колоду, і це нормально: екран
 * лишається з таймером (перелік кроків від #288 бачить лише панель дебагу).
 * Вигадувати факти про дім, якого ми ще не знаємо, — рівно те, чого цей
 * продукт не робить.
 *
 * `listMode` — `Pantry.source`, і він ОБОВ'ЯЗКОВИЙ без замовчування: цією
 * задачею вже двічі виявилось, що читач мовчки не спитав про режим (#300).
 */
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

/**
 * Те саме про ДІМ, без жодного слова про цей прогін.
 *
 * Виділено 08.09, коли той самий екран став на другу роботу -- заповнення
 * комори (#341). Дві картки колоди («твій список», «тримаю межу») описують
 * ЗБІРКУ, і на екрані комори вони були б обіцянкою, якої ніхто не давав:
 * гість нічого не набирав і суми не називав. Решта -- факти з його ж рядків,
 * і вони однакові для обох робіт, тож другий перелік розійшовся б з першим
 * мовчки (#158).
 *
 * КОЛОДА ПОРОЖНЯ, ПОКИ КОМОРИ НЕМАЄ, і це не край, а стан: на першому вході
 * рядків ще немає взагалі, тобто фактів про дім теж. Вигадати їх означало б
 * зробити рівно те, чого цей продукт не робить, -- верхня половина екрана в
 * цей час несе справжні кроки.
 */
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
