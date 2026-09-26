
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

export type Loaded<T> =
  { ok: true; data: T } | { ok: false; message: string; status: number | null };

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

export function loadHealth(): Promise<Loaded<Health>> {
  return link.backend
    ? attempt(checkHealth, "спитати версію бекенда")
    : Promise.resolve({
        ok: false,
        message: "бекенда за цією адресою немає",
        status: null,
      });
}

export function loadProfileRules(): Promise<Loaded<Exclusion[]>> {
  return attempt(listExclusions, "прочитати обмеження з профілю «Сільпо»");
}

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

export function loadPlace(): Promise<Loaded<Place>> {
  return attempt(readPlace, "дізнатися, куди веземо");
}

export function searchPlace(text: string): Promise<Loaded<PlaceOption[]>> {
  return attempt(() => findPlaces(text), "знайти адресу");
}

export function sendPlace(option: PlaceOption): Promise<Loaded<Place>> {
  return attempt(() => setPlace(option), "запам'ятати адресу");
}

export function loadQuota(): Promise<Loaded<Quota>> {
  return attempt(readQuota, "спитати, скільки прогонів лишилось");
}

export function loadModels(): Promise<Loaded<ModelOption[]>> {
  return attempt(listModels, "прочитати перелік моделей");
}

export function loadPantry(cold = false): Promise<Loaded<Pantry>> {
  return attempt(() => listPantry(cold), "прочитати комору");
}

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

export function resolvePantryUnit(label: string): Promise<Loaded<PantryItem>> {
  return attempt(
    () => resolvePantryItem(label),
    "знайти цей вид у твоїх чеках",
  );
}

export function setPantrySource(
  mode: "receipts" | "manual",
): Promise<Loaded<Pantry>> {
  return attempt(() => choosePantrySource(mode), "запам'ятати, чим вести список");
}

export function buildPantryFromPurchases(): Promise<Loaded<Pantry>> {
  return attempt(generatePantry, "скласти список з твоїх покупок");
}

export function nextShoppingList(): Promise<Loaded<NextList>> {
  return attempt(composeNextList, "скласти список на наступну покупку");
}

export function clearPantryList(): Promise<Loaded<Pantry>> {
  return attempt(wipePantryList, "стерти список");
}

export function dropPantryItem(id: string): Promise<Loaded<void>> {
  return attempt(() => forgetPantryItem(id), "прибрати цей рядок");
}

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

export function setBarSource(
  mode: "receipts" | "manual",
): Promise<Loaded<Bar>> {
  return attempt(() => chooseBarSource(mode), "запам'ятати, чим вести бар");
}

export function buildBarFromPurchases(): Promise<Loaded<Bar>> {
  return attempt(generateBar, "скласти бар з твоїх покупок");
}

export function clearBarList(): Promise<Loaded<Bar>> {
  return attempt(wipeBarList, "стерти список бару");
}

export function addBarKind(label: string): Promise<Loaded<Bar>> {
  return attempt(() => addBarItem(label), "додати цей вид у бар");
}

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

export function dropBarKind(id: string): Promise<Loaded<Bar>> {
  return attempt(() => forgetBarItem(id), "прибрати цей рядок");
}


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
  cold = false,
): Promise<Loaded<Pantry>> {
  return attempt(
    () => adjustPantry(id, action, qty, days, group, chain, cold),
    PANTRY_WORK[action],
  );
}

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
