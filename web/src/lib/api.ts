import type {
  AnswerTaken,
  Progress,
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
  Pantry,
  PantryAdjustment,
  PantryItem,
  Place,
  PlaceOption,
  Quota,
  SavedSwap,
  SwapDecision,
  SwapOption,
  NextList,
  WantedRow,
  WeekSpend,
} from "./types";

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

const BY_STATUS: Record<number, string> = {
  429: "поки зайнято — спробуй за кілька секунд",
  500: "щось пішло не так у нас",
  502: "з'єднання із сервером обірвалось — спробуй ще раз",
  503: "сервіс зараз недоступний — спробуй за мить",
  504: "сервер не встиг відповісти — спробуй ще раз",
};

function failure(status: number, body: string, statusText: string): string {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
  }
  return BY_STATUS[status] ?? statusText ?? `не вдалось (${status})`;
}

const PATIENCE_MS = 290_000;

export const QUICK_MS = 20_000;

function timedOut(patience: number): ApiError {
  return new ApiError(
    `сервер мовчить довше ${Math.round(patience / 1000)} с — спробуй ще раз`,
    504,
  );
}

async function request<T>(
  path: string,
  init?: RequestInit,
  patience: number = PATIENCE_MS,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      headers: { "content-type": "application/json" },
      signal: AbortSignal.timeout(patience),
      ...init,
    });
  } catch (exc) {
    if (exc instanceof DOMException && exc.name === "TimeoutError") {
      throw timedOut(patience);
    }
    throw exc;
  }

  if (!response.ok) {
    throw new ApiError(
      failure(response.status, await response.text(), response.statusText),
      response.status,
    );
  }

  return (await response.json()) as T;
}

async function requestVoid(
  path: string,
  init?: RequestInit,
  patience: number = PATIENCE_MS,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      headers: { "content-type": "application/json" },
      signal: AbortSignal.timeout(patience),
      ...init,
    });
  } catch (exc) {
    if (exc instanceof DOMException && exc.name === "TimeoutError") {
      throw timedOut(patience);
    }
    throw exc;
  }
  if (!response.ok) {
    throw new ApiError(
      failure(response.status, await response.text(), response.statusText),
      response.status,
    );
  }
}

export function readProgress(key: string): Promise<Progress> {
  return request<Progress>(`/progress/${encodeURIComponent(key)}`);
}

export function answerProgress(
  key: string,
  questionId: string,
  optionId: string,
): Promise<AnswerTaken> {
  return request<AnswerTaken>(`/progress/${encodeURIComponent(key)}/answer`, {
    method: "POST",
    body: JSON.stringify({ questionId, optionId }),
  });
}

export function buildBasket(payload: BuildRequest): Promise<Basket> {
  return request<Basket>("/basket", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function checkHealth(): Promise<Health> {
  return request<Health>("/health");
}

export function listDeliveryOptions(): Promise<DeliveryOption[]> {
  return request<DeliveryOption[]>("/delivery-options");
}

export function readPlace(): Promise<Place> {
  return request<Place>("/place");
}

export function findPlaces(text: string): Promise<PlaceOption[]> {
  return request<PlaceOption[]>("/place/search", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export function setPlace(option: PlaceOption): Promise<Place> {
  return request<Place>("/place", {
    method: "POST",
    body: JSON.stringify({
      label: option.label,
      latitude: option.latitude,
      longitude: option.longitude,
      id: option.id,
      city: option.city,
      street: option.street,
      house: option.house,
    }),
  });
}

export function readQuota(): Promise<Quota> {
  return request<Quota>("/quota");
}

export function listModels(): Promise<ModelOption[]> {
  return request<ModelOption[]>("/models");
}

export function correctLine(
  runId: string,
  externalProductId: string,
  action: "still_have" | "ran_out_earlier" | "never_again",
): Promise<Basket> {
  return request<Basket>(`/basket/${runId}/correction`, {
    method: "POST",
    body: JSON.stringify({ externalProductId, action }),
  });
}

export function applySwaps(
  runId: string,
  swaps: SwapDecision[],
  remember = false,
): Promise<Basket> {
  return request<Basket>(`/basket/${runId}/swaps`, {
    method: "POST",
    body: JSON.stringify({ swaps, remember }),
  });
}

export function listSavedSwaps(): Promise<SavedSwap[]> {
  return request<SavedSwap[]>("/swaps/saved");
}

export function forgetSavedSwap(id: string): Promise<SavedSwap[]> {
  return request<SavedSwap[]>(`/swaps/saved/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function refillBasket(
  runId: string,
  intents: string[],
  model: string | null,
  answers: ClarifyAnswer[] = [],
): Promise<Basket> {
  return request<Basket>(`/basket/${runId}/refill`, {
    method: "POST",
    body: JSON.stringify({ intents, model, answers }),
  });
}

export function pickForQuestion(
  runId: string,
  intent: string,
  externalProductId: string,
): Promise<Basket> {
  return request<Basket>(`/basket/${runId}/pick`, {
    method: "POST",
    body: JSON.stringify({ intent, externalProductId }),
  });
}

export function takeCheaper(
  runId: string,
  externalProductId: string,
  to: string,
): Promise<Basket> {
  return request<Basket>(`/basket/${runId}/cheaper`, {
    method: "POST",
    body: JSON.stringify({ externalProductId, to }),
  });
}

export function listSwapOptions(
  runId: string,
  lineId: string,
  query?: string,
): Promise<SwapOption[]> {
  const params = new URLSearchParams({ line: lineId });
  if (query?.trim()) params.set("q", query.trim());
  return request<SwapOption[]>(`/basket/${runId}/options?${params}`);
}

export function checkoutBasket(
  runId: string,
  existing: CarryOverState = "asking",
  lines?: Record<string, number>,
  extras?: CheckoutExtra[],
  model?: string | null,
  fast?: boolean | null,
): Promise<CheckoutResult> {
  return request<CheckoutResult>(`/basket/${runId}/checkout`, {
    method: "POST",
    body: JSON.stringify({
      existing,
      ...(lines ? { lines } : {}),
      ...(extras && extras.length > 0 ? { extras } : {}),
      model: model ?? null,
      fast: fast ?? null,
    }),
  });
}

export function listExclusions(): Promise<Exclusion[]> {
  return request<Exclusion[]>("/exclusions");
}

export function listRules(): Promise<Exclusion[]> {
  return request<Exclusion[]>("/rules");
}

export function addRule(label: string, active = true): Promise<Exclusion[]> {
  return request<Exclusion[]>("/rules", {
    method: "POST",
    body: JSON.stringify({ label, active }),
  });
}

export function switchRule(id: string, active: boolean): Promise<Exclusion[]> {
  return request<Exclusion[]>(`/rules/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ active }),
  });
}

export function dropRule(id: string): Promise<Exclusion[]> {
  return request<Exclusion[]>(`/rules/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function listPantry(cold = false): Promise<Pantry> {
  return request<Pantry>(cold ? "/pantry?cold=true" : "/pantry");
}

export function refinePantry(
  progressKey?: string,
  cold = false,
  fast: boolean | null = null,
  answers: Record<string, number> = {},
  covers: Record<string, string[]> = {},
  kinds: Record<string, string> = {},
  seen = 0,
  more = false,
): Promise<Pantry> {
  return request<Pantry>("/pantry/refine", {
    method: "POST",
    body: JSON.stringify({ progressKey, cold, fast, answers, covers, kinds, seen, more }),
  })
}

export function resolvePantryItem(label: string): Promise<PantryItem> {
  return request<PantryItem>("/pantry/manual", {
    method: "POST",
    body: JSON.stringify({ label }),
  });
}

export function choosePantrySource(
  mode: "receipts" | "manual",
): Promise<Pantry> {
  return request<Pantry>(
    "/pantry/source",
    { method: "PUT", body: JSON.stringify({ mode }) },
    QUICK_MS,
  );
}

export function generatePantry(): Promise<Pantry> {
  return request<Pantry>("/pantry/generate", { method: "POST" }, QUICK_MS);
}

export function composeNextList(): Promise<NextList> {
  return request<NextList>("/pantry/next-list", { method: "POST" });
}

export function wipePantryList(): Promise<Pantry> {
  return request<Pantry>("/pantry/items", { method: "DELETE" }, QUICK_MS);
}

export function forgetPantryItem(id: string): Promise<void> {
  return requestVoid(`/pantry/manual/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function readCartState(): Promise<CartState> {
  return request<CartState>("/cart");
}

export function readWeekSpend(): Promise<WeekSpend> {
  return request<WeekSpend>("/week-spend");
}

export function adjustPantry(
  id: string,
  action: PantryAdjustment["action"],
  qty = 0,
  days = 0,
  group = "",
  chain: string[] = [],
  cold = false,
): Promise<Pantry> {
  return request<Pantry>(cold ? "/pantry?cold=true" : "/pantry", {
    method: "PATCH",
    body: JSON.stringify({ id, action, qty, days, group, chain }),
  });
}

export function listWanted(): Promise<WantedRow[]> {
  return request<WantedRow[]>("/list");
}

export function addWanted(label: string, atHome = true): Promise<WantedRow[]> {
  return request<WantedRow[]>("/list", {
    method: "POST",
    body: JSON.stringify({ label, atHome }),
  });
}

export function forgetWanted(id: string): Promise<WantedRow[]> {
  return request<WantedRow[]>(`/list/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function listBar(): Promise<Bar> {
  return request<Bar>("/bar");
}

export function chooseBarSource(mode: "receipts" | "manual"): Promise<Bar> {
  return request<Bar>(
    "/bar/source",
    { method: "PUT", body: JSON.stringify({ mode }) },
    QUICK_MS,
  );
}

export function generateBar(): Promise<Bar> {
  return request<Bar>("/bar/generate", { method: "POST" }, QUICK_MS);
}

export function wipeBarList(): Promise<Bar> {
  return request<Bar>("/bar/items", { method: "DELETE" }, QUICK_MS);
}

export function addBarItem(label: string): Promise<Bar> {
  return request<Bar>("/bar/manual", {
    method: "POST",
    body: JSON.stringify({ label }),
  });
}

export function chooseBarGroup(
  label: string,
  kind: DrinkKind | null,
): Promise<Bar> {
  return request<Bar>("/bar/group", {
    method: "PUT",
    body: JSON.stringify({ label, kind }),
  });
}

export function forgetBarItem(id: string): Promise<Bar> {
  return request<Bar>(`/bar/manual/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export { ApiError };
