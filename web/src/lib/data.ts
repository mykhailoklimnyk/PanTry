
import {
  ApiError,
  adjustPantry,
  applySwaps,
  forgetSavedSwap,
  checkHealth,
  checkoutBasket,
  correctLine,
  dropRule,
  findPlaces,
  choosePantrySource,
  forgetPantryItem,
  composeNextList,
  generatePantry,
  buildBasket,
  addBarItem,
  addWanted,
  chooseBarGroup,
  chooseBarSource,
  forgetBarItem,
  generateBar,
  forgetWanted,
  listBar,
  listSavedSwaps,
  listWanted,
  listDeliveryOptions,
  listExclusions,
  listModels,
  listPantry,
  refinePantry,
  listRules,
  listSwapOptions,
  readCartState,
  readPlace,
  readQuota,
  readWeekSpend,
  pickForQuestion,
  takeCheaper,
  refillBasket,
  resolvePantryItem,
  wipeBarList,
  wipePantryList,
  setPlace,
  switchRule,
  addRule as writeRule,
} from "./api";
import { dropped, link } from "./session.svelte";
import type {
  Bar,
  Basket,
  BuildRequest,
  CarryOverState,
  CartState,
  CheckoutExtra,
  CheckoutResult,
  ClarifyAnswer,
  DeliveryOption,
  DrinkKind,
  Exclusion,
  Health,
  ModelOption,
  NextList,
  Pantry,
  PantryAdjustment,
  PantryItem,
  SavedSwap,
  WantedRow,
  Place,
  PlaceOption,
  Quota,
  SwapDecision,
  SwapOption,
  WeekSpend,
} from "./types";

/**
 * Відмова возить ще й КОД, а не саму лише фразу (#91).
 *
 * `null` означає «не доїхало до сервера» — мережа, офлайн, воркер. Це інша
 * поломка, ніж 500, і лагодиться вона в іншому місці, тож зводити обидві до
 * одного «щось пішло не так» означало б послати шукати не там.
 */
export type Loaded<T> =
  { ok: true; data: T } | { ok: false; message: string; status: number | null };

/**
 * Живий виклик → union.
 *
 * 401 обробляється ТУТ, один раз на весь фронт — дзеркало глобального
 * обробника на бекенді. Інакше цю перевірку довелося б згадати в кожному
 * споживачі, і перший же новий її б забув: доступ зникає посеред роботи
 * (гість вийшов у іншій вкладці, зняв дозвіл у застосунку «Сільпо»), а
 * виглядало б це як випадковий збій одного екрана.
 */
async function attempt<T>(
  work: () => Promise<T>,
  what: string,
): Promise<Loaded<T>> {
  try {
    return { ok: true, data: await work() };
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : `не вдалося ${what}`;
    const status = exc instanceof ApiError ? exc.status : null;
    if (status === 401) dropped(message);
    return { ok: false, message, status };
  }
}

export function loadBasket(request: BuildRequest): Promise<Loaded<Basket>> {
  return attempt(() => buildBasket(request), "зібрати кошик");
}

/**
 * Здоров'я бекенда і його коміт.
 *
 * Єдине, що питається БЕЗ акаунта: версія сервера — не чиїсь дані, а
 * розбіжність із фронтом тиха рівно настільки, наскільки її ніхто не
 * показує. Там, де бекенда немає взагалі, відмова називається словами.
 */
export function loadHealth(): Promise<Loaded<Health>> {
  return link.backend
    ? attempt(checkHealth, "спитати версію бекенда")
    : Promise.resolve({
        ok: false,
        message: "бекенда за цією адресою немає",
        status: null,
      });
}

/**
 * Обмеження з профілю «Сільпо» — чуже налаштування, яке ми показуємо.
 *
 * Окремим лоадером від правил гостя (нижче), бо ці двоє ламаються з різних
 * причин: тут мовчить «Сільпо», там наша база. Один спільний лоадер означав
 * би, що недоступний профіль забирає з екрана й те, що гість написав сам.
 */
export function loadProfileRules(): Promise<Loaded<Exclusion[]>> {
  return attempt(listExclusions, "прочитати обмеження з профілю «Сільпо»");
}

/** Правила, які гість написав словами. Живуть за акаунтом, не за браузером. */
export function loadOwnRules(): Promise<Loaded<Exclusion[]>> {
  return attempt(listRules, "прочитати твої правила");
}

export function saveRule(
  label: string,
  active = true,
): Promise<Loaded<Exclusion[]>> {
  return attempt(() => writeRule(label, active), "зберегти правило");
}

export function toggleRule(
  id: string,
  active: boolean,
): Promise<Loaded<Exclusion[]>> {
  return attempt(() => switchRule(id, active), "зберегти зміну правила");
}

export function deleteRule(id: string): Promise<Loaded<Exclusion[]>> {
  return attempt(() => dropRule(id), "видалити правило");
}

export function loadDeliveryOptions(): Promise<Loaded<DeliveryOption[]>> {
  return attempt(listDeliveryOptions, "прочитати способи отримання");
}

/**
 * Куди веземо і хто збирає.
 *
 * Читається разом зі способами отримання, а не при оформленні: філія міняє
 * асортимент, ціни й залишки, тобто весь кошик.
 */
export function loadPlace(): Promise<Loaded<Place>> {
  return attempt(readPlace, "дізнатися, куди веземо");
}

/** Адреса словами → варіанти. Обирає гість: пошук віддає й інші міста. */
export function searchPlace(text: string): Promise<Loaded<PlaceOption[]>> {
  return attempt(() => findPlaces(text), "знайти адресу");
}

/** Обрана адреса → нове «куди веземо» цілком, разом із філією і словами. */
export function sendPlace(option: PlaceOption): Promise<Loaded<Place>> {
  return attempt(() => setPlace(option), "запам'ятати адресу");
}

/** Стеля живого контуру: числа стану і дія, коли вона спрацювала. */
export function loadQuota(): Promise<Loaded<Quota>> {
  return attempt(readQuota, "спитати, скільки прогонів лишилось");
}

export function loadModels(): Promise<Loaded<ModelOption[]>> {
  return attempt(listModels, "прочитати перелік моделей");
}

export function loadPantry(cold = false): Promise<Loaded<Pantry>> {
  return attempt(() => listPantry(cold), "прочитати комору");
}

/**
 * Друга відповідь комори -- те, чого першій бракувало (#330).
 *
 * Відмова тут не банер: комора вже намальована і вже правдива, а петля лише
 * уточнює. Гучна відмова на цьому місці була б червоним екраном там, де в
 * гостя все гаразд; що петля не приїхала, видно з `refined` і з трейсу.
 */
export function loopPantry(
  progressKey?: string,
  cold = false,
  fast: boolean | null = null,
  answers: Record<string, number> = {},
  covers: Record<string, string[]> = {},
  kinds: Record<string, string> = {},
  seen = 0,
  more = false,
): Promise<Loaded<Pantry>> {
  return attempt(
    () => refinePantry(progressKey, cold, fast, answers, covers, kinds, seen, more),
    "уточнити стан дому",
  );
}

/** Названий руками вид → рядок з одиницею з чеків гостя (#39). */
export function resolvePantryUnit(label: string): Promise<Loaded<PantryItem>> {
  return attempt(
    () => resolvePantryItem(label),
    "знайти цей вид у твоїх чеках",
  );
}

/**
 * Чим наповнюється список комори (#109). Назад -- ПЕРЕрахована комора.
 *
 * Три дії, а не одна з параметром: вони роблять різне і ламаються по-різному
 * («вибір не зберігся» проти «список не склався»), а одна назва на трьох
 * зробила б з причини відмови здогад.
 */
export function setPantrySource(
  mode: "receipts" | "manual",
): Promise<Loaded<Pantry>> {
  return attempt(() => choosePantrySource(mode), "запам'ятати, чим вести список");
}

/** Скласти список з покупок -- явною дією (#109). */
export function buildPantryFromPurchases(): Promise<Loaded<Pantry>> {
  return attempt(generatePantry, "скласти список з твоїх покупок");
}

/** Скласти список на наступну покупку з комори (#306). */
export function nextShoppingList(): Promise<Loaded<NextList>> {
  return attempt(composeNextList, "скласти список на наступну покупку");
}

/** Стерти ВЕСЬ список, доданий руками (#109). */
export function clearPantryList(): Promise<Loaded<Pantry>> {
  return attempt(wipePantryList, "стерти список");
}

/** Прибрати вид, доданий руками (#126). */
export function dropPantryItem(id: string): Promise<Loaded<void>> {
  return attempt(() => forgetPantryItem(id), "прибрати цей рядок");
}

/** Варіанти заміни для рядка: вид на слот прогону або пошук словами. */
export function loadSwapOptions(
  runId: string,
  lineId: string,
  query?: string,
): Promise<Loaded<SwapOption[]>> {
  return attempt(
    () => listSwapOptions(runId, lineId, query),
    "прочитати варіанти заміни",
  );
}

export function loadCartState(): Promise<Loaded<CartState>> {
  return attempt(readCartState, "прочитати кошик акаунта");
}

export function loadWeekSpend(): Promise<Loaded<WeekSpend>> {
  return attempt(readWeekSpend, "порахувати витрати тижня");
}

/** Список на наступну покупку (#110). */
export function loadWanted(): Promise<Loaded<WantedRow[]>> {
  return attempt(listWanted, "прочитати список на покупку");
}

export function keepWanted(label: string, atHome = true): Promise<Loaded<WantedRow[]>> {
  return attempt(() => addWanted(label, atHome), "запам'ятати це на наступну покупку");
}

export function dropWanted(id: string): Promise<Loaded<WantedRow[]>> {
  return attempt(() => forgetWanted(id), "прибрати рядок зі списку");
}

export function loadBar(): Promise<Loaded<Bar>> {
  return attempt(listBar, "прочитати бар");
}

/** Чим наповнюється бар: покупками чи самим гостем (#146). */
export function setBarSource(
  mode: "receipts" | "manual",
): Promise<Loaded<Bar>> {
  return attempt(() => chooseBarSource(mode), "запам'ятати, чим вести бар");
}

/** Скласти бар з покупок -- явною дією з видимим результатом. */
export function buildBarFromPurchases(): Promise<Loaded<Bar>> {
  return attempt(generateBar, "скласти бар з твоїх покупок");
}

/** Стерти ВЕСЬ список бару. Комори це не чіпає: області різні. */
export function clearBarList(): Promise<Loaded<Bar>> {
  return attempt(wipeBarList, "стерти список бару");
}

/** Дописати вид у бар руками. */
export function addBarKind(label: string): Promise<Loaded<Bar>> {
  return attempt(() => addBarItem(label), "додати цей вид у бар");
}

/** Переставити вид бару на іншу полицю (#261). `null` -- зняти своє слово. */
export function setBarGroup(
  label: string,
  kind: DrinkKind | null,
): Promise<Loaded<Bar>> {
  return attempt(
    () => chooseBarGroup(label, kind),
    kind === null
      ? "повернути полицю, яку назвав агент"
      : "запам'ятати, на якій полиці цей вид",
  );
}

/** Прибрати вид, дописаний руками. */
export function dropBarKind(id: string): Promise<Loaded<Bar>> {
  return attempt(() => forgetBarItem(id), "прибрати цей рядок");
}

/**
 * Стан замовлення після «Оформити» (#50).
 *
 * Читається НА ВИМОГУ і на кожне повернення на екран: підписки тут немає
 * навмисно — сходинка міняється раз на десятки хвилин, а нагляд без гостя
 * знято цілком разом із кроном (#117).
 */

/**
 * Правка гостя про рядок.
 *
 * Відповідь — перерахований кошик ЦІЛКОМ і з новим `runId`: правка міняє не
 * лише список, а й суму, поріг доставки та блокер мінімуму.
 */
export function sendCorrection(
  runId: string,
  externalProductId: string,
  action: "still_have" | "ran_out_earlier" | "never_again",
): Promise<Loaded<Basket>> {
  return attempt(
    () => correctLine(runId, externalProductId, action),
    "перерахувати кошик",
  );
}

/**
 * Добір у зібраний кошик: решта тижня або слова гостя.
 *
 * Як і правка, це повноцінний прогін з новим `runId` — тому й відповідь тут
 * кошик цілком, а не самі нові рядки.
 */
/**
 * Погоджені заміни в готовий план (#77).
 *
 * Не прогін: ланцюжок міняє рівно текст мандата, і рахує його
 * детермінований код. Але відповідь усе одно кошик з новим `runId` —
 * «Оформити» записує план, який лежить під id.
 */
export function sendSwaps(
  runId: string,
  swaps: SwapDecision[],
  remember = false,
): Promise<Loaded<Basket>> {
  return attempt(() => applySwaps(runId, swaps, remember), "погодити заміни");
}

export function loadSavedSwaps(): Promise<Loaded<SavedSwap[]>> {
  return attempt(listSavedSwaps, "прочитати погоджені заміни");
}

export function dropSavedSwap(id: string): Promise<Loaded<SavedSwap[]>> {
  return attempt(() => forgetSavedSwap(id), "зняти погодження");
}

export function sendRefill(
  runId: string,
  intents: string[],
  model: string | null,
  answers: ClarifyAnswer[] = [],
): Promise<Loaded<Basket>> {
  return attempt(
    () => refillBasket(runId, intents, model, answers),
    answers.length > 0 ? "врахувати уточнення" : "добрати позиції",
  );
}

/** Обраний гостем товар у відповідь на уточнення (#190). */
export function sendPick(
  runId: string,
  intent: string,
  externalProductId: string,
): Promise<Loaded<Basket>> {
  return attempt(
    () => pickForQuestion(runId, intent, externalProductId),
    "додати обране",
  );
}

/** Гість узяв дешевшу ланку того самого виду (#230). */
export function sendCheaper(
  runId: string,
  externalProductId: string,
  to: string,
): Promise<Loaded<Basket>> {
  return attempt(
    () => takeCheaper(runId, externalProductId, to),
    "узяти дешевше",
  );
}

/**
 * Слово гостя про рядок комори (#73).
 *
 * Відповідь — переоцінена комора ЦІЛКОМ, а не один рядок: слово міняє і
 * порядок (що закінчується — згори), і те, що поїде в кошик наступною
 * збіркою.
 */
const PANTRY_WORK: Record<PantryAdjustment["action"], string> = {
  bought: "запам'ятати, що це вже є",
  qty: "поправити залишок",
  cycle: "запам'ятати, на скільки вистачає",
  forget_cycle: "повернути оцінку з чеків",
  hide: "прибрати цей вид із комори",
  unhide: "повернути вид у комору",
  split: "розділити цей намір",
  unsplit: "згорнути намір назад",
  mandate: "запам'ятати заміну для цього виду",
  forget_mandate: "зняти погоджену заміну",
};

export function sendPantryMark(
  id: string,
  action: PantryAdjustment["action"],
  qty = 0,
  days = 0,
  group = "",
  chain: string[] = [],
): Promise<Loaded<Pantry>> {
  return attempt(
    () => adjustPantry(id, action, qty, days, group, chain),
    PANTRY_WORK[action],
  );
}

/**
 * Записати кошик в акаунт «Сільпо». Оформлює гість сам, за посиланням.
 *
 * `existing` — відповідь на питання про рядки, які вже лежали в кошику
 * (#30). Без неї сервер нічого не пише і повертає саме питання.
 */
export function sendCheckout(
  runId: string,
  existing?: CarryOverState,
  lines?: Record<string, number>,
  extras?: CheckoutExtra[],
  model?: string | null,
  fast?: boolean | null,
): Promise<Loaded<CheckoutResult>> {
  return attempt(
    () => checkoutBasket(runId, existing, lines, extras, model, fast),
    "записати кошик",
  );
}
