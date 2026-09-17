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

/**
 * Чому запит не вдався — людськими словами.
 *
 * ТІЛО, ЯКЕ НЕ НАШЕ, ПОКАЗУВАТИ НЕ МОЖНА. Наше тіло — це JSON з `detail`;
 * усе інше писав хтось інший. Живий тест 03.09: гість натиснув «Оформити» і
 * побачив у банері HTML-сторінку Cloudflare — вона підміняє 502 від origin
 * своєю розміткою, а ми друкували тіло як є (#298). Виглядало це не як
 * «чуже API відмовило», а як зламаний продукт.
 *
 * Тому чуже тіло замінює причина ЗА КОДОМ. Вона навмисно НЕ називає
 * винного: щойно відповідь підмінив посередник, ми вже не знаємо, чи це
 * «Сільпо», чи наше сховище, і вгадувати означало б показати гостю причину,
 * якої ніхто не бачив. Ім'я винного приходить лише в НАШОМУ `detail` — і
 * саме тому сервер більше не віддає 502, який до гостя не доїжджає (#298).
 * Один дім на обидва входи (`request` і `requestVoid`): дві копії цього
 * розбору вже стояли поруч і розійшлися б першою ж правкою.
 */
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

/** Помилка, яку видно ГОСТЮ, а не в консолі: чуже мовчання теж має слова. */
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

/**
 * Те саме, але без тіла у відповіді.
 *
 * `request` завжди розбирає JSON, а 204 його не має: спільна гілка тут
 * упала б на порожньому рядку і показала б гостю збій там, де все
 * спрацювало.
 */
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

/**
 * Зібрати кошик.
 *
 * `exclusions` — id постійних обмежень із профілю, `rules` — правила словами,
 * які написав гість. Друге не перетворюємо на коди навмисно: рішення, чим
 * компенсувати виключену категорію, ухвалює агент, а не фронт.
 */
/**
 * Кроки збірки, поки вона йде (02.09): той самий трейс, що ляже в кошик,
 * але видимий до того, як кошик готовий. Ключ -- той, що поїхав у
 * `BuildRequest.progressKey`.
 */
export function readProgress(key: string): Promise<Progress> {
  return request<Progress>(`/progress/${encodeURIComponent(key)}`);
}

/**
 * Відповідь гостя на питання агента ПОСЕРЕД збірки (#285).
 *
 * Окремим запитом, а не полем наступного прогону: питання ставиться, поки
 * збірка йде, і відповідь має сенс лише доти, доки вона ще може щось
 * змінити. `taken: false` -- питання вже відповіли або збірка пішла далі за
 * стелею часу; це не помилка, і банером воно не стає.
 */
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

/**
 * Здоров'я бекенда — і, головне, з якого він коміта.
 *
 * Яруси деплою їдуть окремо (Workers і Fedora), тож свіжий фронт поверх
 * старого API — стан звичайний і мовчазний. Панель дебагу ставить обидва
 * коміти поруч, і питання «а це вже нова версія?» перестає бути здогадом.
 */
export function checkHealth(): Promise<Health> {
  return request<Health>("/health");
}

/** Способи отримання з порогами й лімітами ваги — читаються до збірки. */
export function listDeliveryOptions(): Promise<DeliveryOption[]> {
  return request<DeliveryOption[]>("/delivery-options");
}

/**
 * Куди веземо і хто збирає.
 *
 * Філія — наслідок адреси, а не налаштування: асортимент, ціни й залишки в
 * кожній свої. Тому це читається ДО збірки, як і способи отримання.
 */
export function readPlace(): Promise<Place> {
  return request<Place>("/place");
}

/**
 * Адреса словами → варіанти з координатами.
 *
 * POST, хоч це й читання: адреса гостя не має їхати в рядку запиту, звідки
 * її збирають логи проксі й історія браузера.
 */
export function findPlaces(text: string): Promise<PlaceOption[]> {
  return request<PlaceOption[]>("/place/search", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

/** Обрана адреса. Живе в сесії — в акаунт «Сільпо» ми її не пишемо. */
export function setPlace(option: PlaceOption): Promise<Place> {
  return request<Place>("/place", {
    method: "POST",
    body: JSON.stringify({
      label: option.label,
      latitude: option.latitude,
      longitude: option.longitude,
      id: option.id,
    }),
  });
}

/** Селектор моделей: перелік живий, з Bedrock. Порядок вирішує бекенд. */
/**
 * Скільки прогонів лишилось і що робити, коли не лишилось (#34).
 *
 * Ні MCP, ні моделі — самий лічильник, тож читається на старті разом з
 * рештою. Стеля, про яку дізнаються рівно в мить відмови, це та сама тиша,
 * тільки з затримкою.
 */
export function readQuota(): Promise<Quota> {
  return request<Quota>("/quota");
}

export function listModels(): Promise<ModelOption[]> {
  return request<ModelOption[]>("/models");
}

/**
 * Правка гостя. Не фільтр: прибрали молочку — агент компенсує білок і кальцій
 * з інших категорій, тому відповідь це завжди перерахований кошик цілком.
 */
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

/**
 * Добрати позиції в уже зібраний кошик — без повної перезбірки.
 *
 * Порожній `intents` означає «закрити решту тижня»: сервер бере те, що стеля
 * звичного кошика відклала, і перелічувати це ще й тут означало б дати двом
 * спискам розійтися. Непорожній — слова гостя прямо в кошику (#13).
 *
 * Відповідь — кошик ЦІЛКОМ і з новим `runId`: рядок додався, а разом з ним
 * змінились сума, вага, поріг доставки і блокер мінімуму.
 */
/**
 * Погоджені заміни в готовий план — без перезбірки (#77).
 *
 * Ланцюжок не міняє ні складу кошика, ні цін, ні слота: він міняє рівно
 * текст мандата, а рахує його детермінований код на сервері. Тому це не
 * прогін — ні мережі до «Сільпо», ні моделі, мілісекунди замість тридцяти
 * секунд. Відповідь усе одно кошик з новим `runId`: «Оформити» записує той
 * план, який лежить під id, і мандат мусить поїхати саме перерахований.
 */
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

/** Що погоджено НАДАЛІ (#224): діє на кожну збірку, поки гість не зняв. */
export function listSavedSwaps(): Promise<SavedSwap[]> {
  return request<SavedSwap[]>("/swaps/saved");
}

/** Зняти погодження з виду -- передумав. Прибрати можна те, що видно (#126). */
export function forgetSavedSwap(id: string): Promise<SavedSwap[]> {
  return request<SavedSwap[]>(`/swaps/saved/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function refillBasket(
  runId: string,
  intents: string[],
  model: string | null,
  /**
   * Відповіді на уточнення, які цей добір закриває (#244). Живий тест
   * 01.09: дотик по чипу вузла коштував 30,5 с і повний виклик моделі --
   * перезбірку ВСЬОГО кошика заради одного наміру, решту якого гість уже
   * побачив і прийняв.
   */
  answers: ClarifyAnswer[] = [],
): Promise<Basket> {
  return request<Basket>(`/basket/${runId}/refill`, {
    method: "POST",
    body: JSON.stringify({ intents, model, answers }),
  });
}

/**
 * Гість обрав ТОВАР у відповідь на уточнення (#190).
 *
 * Не перезбірка: рядок відомий цілком, і сервер лише перераховує числа.
 * Той самий клас, що погоджені заміни, — новий `runId` без виклику моделі.
 */
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

/**
 * Гість узяв ДЕШЕВШУ ланку того самого виду (#230).
 *
 * Не режим і не перезбірка: товар названий рядком, а сервер лише міняє його
 * і перераховує числа. Глобального перемикача «брати дешевше» немає
 * свідомо — виміряно, що він зробив би чек більшим у третині випадків, у
 * яких спрацював.
 */
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

/**
 * Чим ще можна закрити рядок — вид цілком на слот ЦЬОГО прогону.
 *
 * `runId` тут не формальність: слот і філію бере сервер із плану, бо
 * асортимент прив'язаний до вікна доставки. `q` — пошук словами, коли гість
 * шукає щось конкретне і виду замало.
 */
export function listSwapOptions(
  runId: string,
  lineId: string,
  query?: string,
): Promise<SwapOption[]> {
  const params = new URLSearchParams({ line: lineId });
  if (query?.trim()) params.set("q", query.trim());
  return request<SwapOption[]>(`/basket/${runId}/options?${params}`);
}

/**
 * Записати зібраний кошик в акаунт «Сільпо».
 *
 * Оформлення робить гість сам — API «Сільпо» замовлень не створює. Тому
 * відповідь це не «замовлено», а звіт: скільки рядків поїхало, що лишилось
 * тут і чому, і посилання, за яким гість підтверджує.
 *
 * `runId` веде до плану на сервері: писати в «Сільпо» можна лише за UUID,
 * а в кошику, який бачить гість, живуть артикули.
 *
 * `existing` — що робити з рядками, які вже лежали в кошику (#30). При
 * `asking` не пишеться нічого, а відповідь це не звіт, а питання з
 * переліком; друге натискання їде з відповіддю гостя.
 */
export function checkoutBasket(
  runId: string,
  existing: CarryOverState = "asking",
  /**
   * Кількості з екрана артикулом, 0 -- прибрано (02.09). Правка числа -- не
   * нова задача для агента: сервер накладає її на свій план перед записом,
   * і «Оформити» не гасне через «-1» на одній позиції.
   */
  lines?: Record<string, number>,
  /**
   * Докинуте на екрані після збірки (11.09): до порога доставки або з бару.
   * Той самий клас, що `lines`: у плані під `runId` цих карток немає, і
   * сервер бере їх з полиці слота перед записом -- замість поради
   * «перезбери» в погашеній кнопці без кнопки перезбірки поруч.
   */
  extras?: CheckoutExtra[],
  /** Модель і швидкий режим -- для докидання до столу після запису (11.09). */
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

/**
 * Обмеження з профілю «Сільпо». Тільки читання: своєї копії ми не тримаємо,
 * бо знята в їхньому застосунку галочка мусить зникнути і в нас.
 */
export function listExclusions(): Promise<Exclusion[]> {
  return request<Exclusion[]>("/exclusions");
}

/**
 * Правила, які гість написав СЛОВАМИ. Окремий шлях від обмежень профілю
 * навмисно: різні джерела з різними правами і з різними причинами мовчати —
 * склеєні, вони забирали б одне одного з собою в помилку (#45).
 *
 * Кожна правка повертає ВЕСЬ список: правила живуть на сервері, і місцевий
 * список після відповіді має дорівнювати серверному, а не своїй здогадці
 * про нього. Друга вкладка інакше розходиться мовчки.
 */
export function listRules(): Promise<Exclusion[]> {
  return request<Exclusion[]>("/rules");
}

export function addRule(label: string, active = true): Promise<Exclusion[]> {
  return request<Exclusion[]>("/rules", {
    method: "POST",
    body: JSON.stringify({ label, active }),
  });
}

/** Id — відбиток слів, не самі слова: шлях запиту лишається в логах проксі. */
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

/**
 * ДРУГА відповідь комори: петля, яка доводить стан дому (#330).
 *
 * Окремим запитом, а не полем у `/pantry`: перша відмальовка -- головний
 * екран, і 3,3 с теплого кешу мусять лишитись теплими. Гість бачить комору
 * одразу, а те, чого їй бракує, приїжджає другою відповіддю.
 */
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

/**
 * Названий руками вид → рядок комори з одиницею з ЙОГО чеків.
 *
 * Окремий виклик, а не поле в `/pantry`: історія важить п'ять сторінок
 * чеків, і платити за неї на кожному відкритті комори заради дії, яка
 * трапляється зрідка, немає за що (#39).
 */
export function resolvePantryItem(label: string): Promise<PantryItem> {
  return request<PantryItem>("/pantry/manual", {
    method: "POST",
    body: JSON.stringify({ label }),
  });
}

/**
 * Чим наповнюється список комори: покупками чи самим гостем (#109).
 *
 * Назад їде ПЕРЕрахована комора, а не «ок»: у режимі гостя список -- це вже
 * інші рядки, і другий запит за ними був би другим читанням тих самих п'яти
 * сторінок покупок (#145).
 */
export function choosePantrySource(
  mode: "receipts" | "manual",
): Promise<Pantry> {
  return request<Pantry>(
    "/pantry/source",
    { method: "PUT", body: JSON.stringify({ mode }) },
    QUICK_MS,
  );
}

/** Скласти список з покупок -- явною дією з видимим результатом (#109). */
export function generatePantry(): Promise<Pantry> {
  return request<Pantry>("/pantry/generate", { method: "POST" }, QUICK_MS);
}

/**
 * Скласти список НА НАСТУПНУ ПОКУПКУ з комори (#306).
 *
 * Відповідь несе не лише рядки, а й ЩО ЗМІНИЛОСЬ: «веде» означає сказане
 * вголос, а не мовчазний перезапис списку, у якому лежить слово гостя.
 */
export function composeNextList(): Promise<NextList> {
  return request<NextList>("/pantry/next-list", { method: "POST" });
}

/**
 * Стерти ВЕСЬ список, доданий руками.
 *
 * Рядків з покупок це не чіпає за побудовою: видаляти нема чого, комора
 * рахує їх щоразу заново (#124). Тому й відповідь -- комора, а не порожнеча.
 */
export function wipePantryList(): Promise<Pantry> {
  return request<Pantry>("/pantry/items", { method: "DELETE" }, QUICK_MS);
}

/**
 * Прибрати вид, доданий руками (#126).
 *
 * Відповідь без тіла: рядок існує рівно тому, що про нього є запис, тож
 * знявши запис, сервер не має що переказувати. Комору назад не тягнемо —
 * видалення рядка гостя не міняє ні циклів, ні порядку решти, а перерахунок
 * коштував би п'ять сторінок чеків заради нічого.
 */
export function forgetPantryItem(id: string): Promise<void> {
  return requestVoid(`/pantry/manual/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/**
 * Що вже лежить у кошику акаунта. Два виклики і жодної збірки: кнопка входу
 * Б мусить знати, чи є що доводити до дверей, ДО кліку (#53).
 */
export function readCartState(): Promise<CartState> {
  return request<CartState>("/cart");
}

/**
 * Скільки вже витрачено цього тижня — за чеками.
 *
 * Читається на вимогу, коли гість відкрив панель бюджету: три виклики MCP
 * заради одного рядка не мають висіти на кожному вході (#56).
 */
export function readWeekSpend(): Promise<WeekSpend> {
  return request<WeekSpend>("/week-spend");
}

/**
 * Слово гостя про рядок комори: «вже купив» або «лишилось стільки» (#73).
 *
 * Правка дорожча за правку кошика: вона міняє не один прогін, а вхідні дані
 * всіх наступних. Тому відповідь — переоцінена комора цілком.
 */
export function adjustPantry(
  id: string,
  action: PantryAdjustment["action"],
  qty = 0,
  days = 0,
  group = "",
  chain: string[] = [],
): Promise<Pantry> {
  return request<Pantry>("/pantry", {
    method: "PATCH",
    body: JSON.stringify({ id, action, qty, days, group, chain }),
  });
}

/**
 * Список на наступну покупку (#110): що гість вирішив узяти обов'язково.
 *
 * Не комора: комора каже, КОЛИ вид закінчиться (прогноз з циклів), а тут
 * рішення, у якому нема в чому помилятись. Тому рядок після покупки згорає,
 * а рядок комори лишається.
 */
export function listWanted(): Promise<WantedRow[]> {
  return request<WantedRow[]>("/list");
}

/** Дописати рядок. Назад їде ВЕСЬ список -- як і в решти дій гостя.
 *
 * `atHome` -- куди рядок поїде ПІСЛЯ покупки (#238). Повторний запис того
 * самого слова з іншим прапорцем і є перемикач: окремого шляху немає, бо
 * другий шлях до одного рядка мав би чим розійтися з першим.
 */
export function addWanted(label: string, atHome = true): Promise<WantedRow[]> {
  return request<WantedRow[]>("/list", {
    method: "POST",
    body: JSON.stringify({ label, atHome }),
  });
}

/** Зняти рядок руками -- передумав. Друга дорога -- покупка: там згорає сам. */
export function forgetWanted(id: string): Promise<WantedRow[]> {
  return request<WantedRow[]>(`/list/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/** Що з алкоголю гість уже брав. Тільки пам'ять про звички, не підбір. */
export function listBar(): Promise<Bar> {
  return request<Bar>("/bar");
}

/**
 * Чим наповнюється бар: покупками чи самим гостем (#146).
 *
 * Прапорець СВІЙ, не спільний з коморою: алкоголь беруть нерівно і не тільки
 * в «Сільпо», тож вести бар руками і лишити комору на чеках -- нормальний
 * стан, а спільний прапорець його забороняв би.
 */
export function chooseBarSource(mode: "receipts" | "manual"): Promise<Bar> {
  return request<Bar>(
    "/bar/source",
    { method: "PUT", body: JSON.stringify({ mode }) },
    QUICK_MS,
  );
}

/** Скласти бар з покупок -- явною дією з видимим результатом (#146). */
export function generateBar(): Promise<Bar> {
  return request<Bar>("/bar/generate", { method: "POST" }, QUICK_MS);
}

/** Стерти ВЕСЬ список бару. Комори це не чіпає: області різні. */
export function wipeBarList(): Promise<Bar> {
  return request<Bar>("/bar/items", { method: "DELETE" }, QUICK_MS);
}

/**
 * Дописати вид у бар руками.
 *
 * Назад їде ВЕСЬ бар, а не сам рядок, -- і це відмінність від комори (#126):
 * групу напою називає модель, тобто рядок стає рядком лише після називання.
 * Рядок без групи, який стрибне в інший блок при наступному читанні,
 * виглядав би як зламаний екран.
 */
export function addBarItem(label: string): Promise<Bar> {
  return request<Bar>("/bar/manual", {
    method: "POST",
    body: JSON.stringify({ label }),
  });
}

/**
 * Переставити вид бару на іншу полицю: «це не лікер, це ром» (#261).
 *
 * Їде ПІДПИС, а не id рядка: id це `група|вид`, тобто саме те, що слово й
 * міняє. `null` -- зняти своє слово і повернутись до здогаду моделі.
 */
export function chooseBarGroup(
  label: string,
  kind: DrinkKind | null,
): Promise<Bar> {
  return request<Bar>("/bar/group", {
    method: "PUT",
    body: JSON.stringify({ label, kind }),
  });
}

/** Прибрати вид, дописаний руками. Рядок з чеків так прибрати не можна. */
export function forgetBarItem(id: string): Promise<Bar> {
  return request<Bar>(`/bar/manual/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export { ApiError };
