
import type {
  Basket,
  BuildRequest,
  CheaperRequest,
  CorrectionRequest,
  PickRequest,
  RefillRequest,
  SwapsRequest,
} from "./types";

/** Збірка: на сервер поїхав намір цілком. */
export interface BuildRun {
  kind: "build";
  request: BuildRequest;
  basket: Basket;
}

/** Правка одного рядка: сервер перерахував план і віддав новий `runId`. */
export interface CorrectionRun {
  kind: "correction";
  request: CorrectionRequest;
  basket: Basket;
}

/** Добір: маленький прогін по нових намірах, злитий у наявний план. */
export interface RefillRun {
  kind: "refill";
  request: RefillRequest;
  basket: Basket;
}

/**
 * Обраний гостем товар у відповідь на уточнення (#190).
 *
 * У списку прогонів з тієї ж причини, що й заміни: «Оформити» записує план
 * під тим id, що лежить у кошику. Але це НЕ прогін конвеєра -- ні пошуку, ні
 * моделі: гість назвав рядок, решта арифметика.
 */
export interface PickRun {
  kind: "pick";
  request: PickRequest;
  basket: Basket;
}

/**
 * Гість узяв дешевшу ланку того самого виду (#230).
 *
 * У списку -- з тієї ж причини, що правка і вибір: «Оформити» записує план
 * під тим `runId`, який лежить у кошику, і панель, у якій цього кроку не
 * видно, показує вже не той план, що поїде.
 */
export interface CheaperRun {
  kind: "cheaper";
  request: CheaperRequest;
  basket: Basket;
}

/**
 * Погоджені заміни: не прогін конвеєра, але новий `runId` (#77).
 *
 * У списку він мусить бути з тієї ж причини, що й правка: «Оформити»
 * записує план під тим id, який лежить у кошику, і панель, у якій його не
 * видно, показує вже не той план, що поїде.
 */
export interface SwapsRun {
  kind: "swaps";
  request: SwapsRequest;
  basket: Basket;
}

/**
 * Спроба, яка не дала кошика (#91).
 *
 * Досі в список потрапляла лише УСПІШНА відповідь, тож губився рівно той
 * запит, що зламав, — єдиний, з якого падіння можна відтворити. Гість бачив
 * плашку «помилка», а що саме поїхало на сервер, не знав ніхто.
 *
 * Окремий вид, а не прогін із порожнім кошиком: у нього немає ні складу, ні
 * трейсу, і рядок «0 рядків · 0 ₴» серед справжніх прогонів читався б як
 * зібраний порожній кошик.
 */
export interface FailedRun {
  kind: "failed";
  /** Що саме поїхало: у невдалої спроби це єдиний спосіб сказати. */
  what: RunKind;
  request:
    | BuildRequest
    | CheaperRequest
    | CorrectionRequest
    | PickRequest
    | RefillRequest
    | SwapsRequest;
  /** Код відповіді. `null` — до сервера не доїхало взагалі. */
  status: number | null;
  message: string;
  /** Час спроби: більше його взяти нема звідки — трейсу тут немає. */
  at: number;
}

/** Прогін, який дав кошик. Усе, що рахує різницю, працює тільки з ними. */
export type DoneRun =
  BuildRun | CheaperRun | CorrectionRun | PickRun | RefillRun | SwapsRun;

export type RunKind = DoneRun["kind"];

export type Run = DoneRun | FailedRun;
