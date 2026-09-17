
import type { Page, Route } from "@playwright/test";

import type {
  Bar,
  BarItem,
  Basket,
  CarryOverLine,
  CartLine,
  CheckoutResult,
  Postponed,
  CartState,
  DeliveryOption,
  DrinkKind,
  Exclusion,
  Health,
  ModelOption,
  Pantry,
  PantryItem,
  Place,
  PlaceOption,
  PriceFork,
  Quota,
  SavedSwap,
  SpendTarget,
  SwapOption,
  TraceStep,
  WeekSpend,
} from "../src/lib/types";


export const LINES: CartLine[] = [
  {
    externalProductId: "demo-milk",
    name: "Молоко Селянське 2,5%",
    qty: 2,
    unit: "шт",
    step: null,
    price: 56.9,
    basePrice: 65.9,
    saleNote: "-18 ₴ від 2-х",
    weightKg: 0.95,
    imageUrl: null,
    cardUrl: null,
    reason: "cycle",
    explanation: "закінчиться ~19.08 · береш кожні 6 днів",
    explanationDetail:
      "Порахував за 40 чеками: середній цикл і дата останньої покупки.",
    confidence: 0.92,
    atRisk: false,
    needsApproval: false,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [
      {
        externalProductId: "demo-milk-yagotyn",
        name: "Молоко Яготинське 2,6%",
        price: 75.99,
        ratio: "900г",
        stock: 9,
        available: true,
        imageUrl: null,
        cardUrl: null,
        sameKind: true,
        kind: "молоко",
        sliced: false,
        byWeight: false,
      },
      {
        externalProductId: "demo-milk-galychyna",
        name: "Молоко Галичина 2,5%",
        price: 68.5,
        ratio: "870г",
        stock: 0,
        available: false,
        imageUrl: null,
        cardUrl: null,
        sameKind: true,
        kind: "молоко",
        sliced: false,
        byWeight: false,
      },
      {
        externalProductId: "demo-milk-farm",
        name: "Молоко фермерське розливне",
        price: 1399,
        ratio: "100г",
        stock: 4.9,
        available: true,
        imageUrl: null,
        cardUrl: null,
        sameKind: true,
        kind: "молоко",
        sliced: false,
        byWeight: true,
      },
    ],
    consideredTotal: 4,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
  {
    externalProductId: "demo-feed",
    name: "Корм Club 4 Paws кролик",
    qty: 7,
    unit: "шт",
    step: null,
    price: 12.99,
    basePrice: null,
    saleNote: null,
    weightKg: 0.085,
    imageUrl: null,
    cardUrl: null,
    reason: "cycle",
    explanation: "залишок 4 у твоїй філії · заміна погоджена наперед",
    explanationDetail:
      "Заміну підібрано за твоєю історією — той самий смак, фасовка 85 г. Ти вже брав її двічі.",
    confidence: 0.88,
    atRisk: true,
    needsApproval: false,
    chain: [
      {
        externalProductId: "demo-feed-85",
        name: "Club 4 Paws кролик 85 г",
        source: "history",
        price: 21.9,
        ratio: "85г",
        byWeight: false,
      },
      {
        externalProductId: "demo-feed-turkey",
        name: "Club 4 Paws індичка 85 г",
        source: "history",
        price: 22.5,
        ratio: "85г",
        byWeight: false,
      },
      {
        externalProductId: "demo-feed-purina",
        name: "Purina One кролик 85 г",
        source: "replacements",
        price: null,
        ratio: null,
        byWeight: false,
      },
    ],
    mandate: "Якщо не вистачить — той самий смак 85 г, до 7 шт. Не дзвонити.",
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
  {
    externalProductId: "demo-yogurt",
    name: "Йогурт Активіа натуральний",
    qty: 4,
    unit: "шт",
    step: null,
    price: 34.9,
    basePrice: null,
    saleNote: null,
    weightKg: 0.26,
    imageUrl: null,
    cardUrl: null,
    reason: "frequency",
    explanation: "потребує погодження заміни",
    explanationDetail:
      "звичне — 5 чеків в історії. Погодь заміну або увімкни авто-заміну, інакше не повезу",
    confidence: 0.74,
    atRisk: true,
    needsApproval: true,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
  {
    externalProductId: "demo-water",
    name: "Вода Карпатська Джерельна",
    qty: 6,
    unit: "шт",
    step: null,
    price: 28.99,
    basePrice: null,
    saleNote: null,
    weightKg: 1,
    imageUrl: null,
    cardUrl: null,
    reason: "frequency",
    explanation: "береш у 8 з 10 замовлень",
    explanationDetail:
      "Цикл нестабільний, але позиція повторюється майже щоразу.",
    confidence: 0.8,
    atRisk: false,
    needsApproval: false,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
  {
    externalProductId: "demo-rice",
    name: "Рис Преміа довгозернистий",
    qty: 1,
    unit: "уп",
    step: null,
    price: 54.9,
    basePrice: null,
    saleNote: null,
    weightKg: 1,
    imageUrl: null,
    cardUrl: null,
    reason: "at_home",
    explanation: "схоже, ще є вдома",
    explanationDetail:
      "За чеками ти брав це 9 днів тому, а витрачаєш за три тижні. Додай, якщо вже закінчилось.",
    confidence: 0.35,
    atRisk: false,
    needsApproval: false,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
  {
    externalProductId: "demo-eggs",
    name: "Яйця С0, 10 шт",
    qty: 2,
    unit: "уп",
    step: null,
    price: 59.9,
    basePrice: null,
    saleNote: null,
    weightKg: 0.6,
    imageUrl: null,
    cardUrl: null,
    reason: "cycle",
    explanation: "закінчиться ~18.08 · береш кожні 7 днів",
    explanationDetail:
      "Порахував за 40 чеками: середній цикл і дата останньої покупки.",
    confidence: 0.9,
    atRisk: false,
    needsApproval: false,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
  {
    externalProductId: "demo-coffee",
    name: "Кава Lavazza Crema e Gusto",
    qty: 1,
    unit: "шт",
    step: null,
    price: 245,
    basePrice: 289,
    saleNote: "акція -15%",
    weightKg: 0.25,
    imageUrl: null,
    cardUrl: null,
    reason: "frequency",
    explanation: "береш у 9 з 10 замовлень",
    explanationDetail:
      "Акція діє з карткою «Власний рахунок» — вона вже прив'язана.",
    confidence: 0.86,
    atRisk: false,
    needsApproval: false,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
  {
    externalProductId: "demo-bread",
    name: "Хліб Київський житній нарізаний",
    qty: 3,
    unit: "шт",
    step: null,
    price: 29.9,
    basePrice: null,
    saleNote: null,
    weightKg: 0.4,
    imageUrl: null,
    cardUrl: null,
    reason: "cycle",
    explanation: "закінчиться ~16.08 · береш кожні 3 дні",
    explanationDetail: "Найкоротший цикл у наборі — тому три штуки, а не одна.",
    confidence: 0.94,
    atRisk: false,
    needsApproval: false,
    chain: [
      {
        externalProductId: "demo-bread-darnytskyi",
        name: "Хліб Дарницький",
        source: "similar",
        price: 32.4,
        ratio: "700г",
        byWeight: false,
      },
    ],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: true,
    slicingNote: "у твоїх чеках цей вид 7 без нарізки, 1 нарізаним",
    cheaper: null,
  },
  {
    externalProductId: "demo-paper",
    name: "Папір туалетний Zewa 8 рул.",
    qty: 1,
    unit: "уп",
    step: null,
    price: 189,
    basePrice: null,
    saleNote: null,
    weightKg: 0.9,
    imageUrl: null,
    cardUrl: null,
    reason: "at_home",
    explanation: "схоже, ще є вдома",
    explanationDetail:
      "Брав 9 днів тому вісім рулонів. За твоїм темпом їх вистачить ще на дев'ять днів.",
    confidence: 0.3,
    atRisk: false,
    needsApproval: false,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
  {
    externalProductId: "demo-cheese",
    name: "Сир Джюгас 12 міс.",
    qty: 1,
    unit: "шт",
    step: null,
    price: 164.5,
    basePrice: null,
    saleNote: null,
    weightKg: 0.2,
    imageUrl: null,
    cardUrl: null,
    reason: "frequency",
    explanation: "береш у 6 з 10 замовлень",
    explanationDetail:
      "Минулого разу не приїхав — тому цього разу з мандатом на заміну.",
    confidence: 0.62,
    atRisk: false,
    needsApproval: false,
    chain: [
      {
        externalProductId: "demo-cheese-24",
        name: "Джюгас 24 міс.",
        source: "similar",
        price: null,
        ratio: null,
        byWeight: false,
      },
      {
        externalProductId: "demo-cheese-grana",
        name: "Grana Padano 200 г",
        source: "similar",
        price: null,
        ratio: null,
        byWeight: false,
      },
    ],
    mandate:
      "Якщо немає — витриманіший той самий або Grana Padano. Не дзвонити.",
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
  {
    externalProductId: "demo-bananas",
    name: "Банани",
    qty: 1.2,
    unit: "кг",
    step: 0.4,
    price: 48.9,
    basePrice: null,
    saleNote: null,
    weightKg: 1,
    imageUrl: null,
    cardUrl: null,
    reason: "cycle",
    explanation: "закінчиться ~17.08 · береш кожні 5 днів",
    explanationDetail:
      "Вага з попередніх чеків: ти щоразу береш близько 1,2 кг.",
    confidence: 0.83,
    atRisk: false,
    needsApproval: false,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
  {
    externalProductId: "demo-oil",
    name: "Олія оливкова Monini 0,5 л",
    qty: 1,
    unit: "шт",
    step: null,
    price: 279,
    basePrice: 319,
    saleNote: "акція до 17.08",
    weightKg: 0.5,
    imageUrl: null,
    cardUrl: null,
    reason: "cycle",
    explanation: "закінчиться ~22.08 · береш кожні 24 дні",
    explanationDetail:
      "До кінця циклу ще тиждень, але акція закінчиться раніше — тому беремо зараз.",
    confidence: 0.71,
    atRisk: false,
    needsApproval: false,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
];

const TRACE: TraceStep[] = [
  {
    id: "step-plan",
    seq: 7,
    tool: "agent.plan",
    args: {
      кроків: 15,
      джерело: "model",
      план:
        "history.receipts -> history.orders -> history.model -> " +
        "intents.compose -> shelf.by_article -> decide.pick -> cart.write -> " +
        "cart.reread; знято: cart.revalidate (немає входу: chains)",
    },
    durationMs: 1120,
    calls: null,
    tokensIn: null,
    tokensOut: null,
    resultSummary: "план від моделі, знято 1: 15 кроків",
    decision: "який крок і в якому порядку — рішення моделі; інваріанти — код",
    tag: "план моделі",
    tagTone: "good",
    externalProductId: null,
    prompt: "plan@ab12cd34",
    question: null,
  },
  {
    id: "step-history",
    seq: 1,
    tool: "get_orders_history",
    args: { months: 3 },
    durationMs: 1600,
    calls: 0,
    tokensIn: null,
    tokensOut: null,
    resultSummary: "40 чеків, 3 міс",
    decision: null,
    tag: null,
    tagTone: "muted",
    externalProductId: null,
    prompt: null,
    question: null,
  },
  {
    id: "step-depletion",
    seq: 2,
    tool: "predict_depletion",
    args: { products: 63 },
    durationMs: 2400,
    calls: null,
    tokensIn: null,
    tokensOut: null,
    resultSummary: "63 товари, цикли 3–24 дні",
    decision: null,
    tag: null,
    tagTone: "muted",
    externalProductId: null,
    prompt: null,
    question: null,
  },
  {
    id: "step-batch",
    seq: 3,
    tool: "find_products_batch",
    args: { ids: 17 },
    durationMs: 400,
    calls: null,
    tokensIn: null,
    tokensOut: null,
    resultSummary:
      "Від двох штук ціна 56,90 замість 65,90. Твій цикл — 6 днів, друга пачка встигне до кінця терміну.",
    decision: "Взяв молоко 2 шт замість 1",
    tag: "вигода 18 ₴",
    tagTone: "good",
    externalProductId: "demo-milk",
    prompt: null,
    question: null,
  },
  {
    id: "step-cycles",
    seq: 0,
    tool: "core.cycles",
    args: {},
    durationMs: null,
    calls: null,
    tokensIn: null,
    tokensOut: null,
    resultSummary: "за циклом ще не мало закінчитись: Молоко",
    decision: "Порахував залишок з циклів",
    tag: "мінус 1",
    tagTone: "muted",
    externalProductId: null,
    prompt: null,
    question: null,
  },
  {
    id: "step-pantry",
    seq: 4,
    tool: "get_pantry_state",
    args: {},
    durationMs: 600,
    calls: null,
    tokensIn: null,
    tokensOut: null,
    resultSummary:
      "За чеками ти брав їх 9 днів тому, а витрачаєш за три тижні. Швидше за все, ще стоять у коморі.",
    decision: "Не додав рис і туалетний папір",
    tag: "мінус 2 позиції",
    tagTone: "muted",
    externalProductId: null,
    prompt: null,
    question: null,
  },
  {
    id: "step-replacements",
    seq: 5,
    tool: "get_replacements",
    args: { externalProductId: "demo-feed" },
    durationMs: 800,
    calls: null,
    tokensIn: null,
    tokensOut: null,
    resultSummary:
      "У твоїй філії залишок 4 з 7. Якщо не вистачить, збирач візьме той самий смак 85 г — ти вже брав його двічі.",
    decision: "Погодив заміну корму наперед",
    tag: "ризик",
    tagTone: "warn",
    externalProductId: "demo-feed",
    prompt: null,
    question: null,
  },
  {
    id: "step-slots",
    seq: 6,
    tool: "silpo_get_time_slots",
    args: {
      deliveryTypes: ["delivery"],
      limit: 20,
      вікно: "2026-08-14T08:00:00+00:00 — 2026-08-14T10:00:00+00:00",
    },
    durationMs: 300,
    calls: null,
    tokensIn: null,
    tokensOut: null,
    resultSummary: "обрано слот пт 11:00–13:00 — вільних 7 з 20 найближчих",
    decision: "перший вільний із 7 у 20 найближчих",
    tag: "не з кошика",
    tagTone: "muted",
    externalProductId: null,
    prompt: null,
    question: null,
  },
];

export const TOPUP_ITEMS: CartLine[] = [
  {
    externalProductId: "demo-buckwheat",
    name: "Гречка Сквирянка 800 г",
    qty: 1,
    unit: "уп",
    step: null,
    price: 44.9,
    basePrice: null,
    saleNote: null,
    weightKg: 0.8,
    imageUrl: null,
    cardUrl: null,
    reason: "topup",
    explanation: "докинуто до порога безкоштовної доставки",
    explanationDetail:
      "Береш приблизно раз на місяць, термін придатності довгий — не зіпсується, поки дійде черга.",
    confidence: 0.5,
    atRisk: false,
    needsApproval: false,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
];

export const DELIVERY: DeliveryOption[] = [
  {
    id: "DeliveryHome",
    label: "кур'єр",
    note: "на адресу, слот 2 години",
    cost: 59,
    minOrder: 300,
    threshold: 1375,
    maxWeightKg: 30,
    available: true,
    unavailableReason: null,
  },
  {
    id: "SelfPickup",
    label: "самовивіз",
    note: "твоя філія, готово за 2 години",
    cost: 0,
    minOrder: null,
    threshold: null,
    maxWeightKg: null,
    available: true,
    unavailableReason: null,
  },
  {
    id: "NovaPoshta",
    label: "Нова пошта",
    note: "відділення, 1–2 дні · без швидкопсувного",
    cost: 89,
    minOrder: 500,
    threshold: 2000,
    maxWeightKg: 20,
    available: true,
    unavailableReason: null,
  },
  {
    id: "DeliveryExpressByPromise",
    label: "експрес",
    note: "за 90 хвилин",
    cost: 149,
    minOrder: 400,
    threshold: null,
    maxWeightKg: 10,
    available: false,
    unavailableReason: "немає вільних кур'єрів на сьогодні",
  },
];

/** Доставка після переходу порога — символічна гривня. */
const DELIVERY_AFTER = 1;

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

const buying = LINES.filter((line) => line.reason !== "at_home");
export const TOTAL = round(buying.reduce((sum, l) => sum + l.qty * l.price, 0));
const BASE_TOTAL = round(
  buying.reduce((sum, l) => sum + l.qty * (l.basePrice ?? l.price), 0),
);

/**
 * Кошик під обраний спосіб отримання.
 *
 * Числа рахуються з рядків, а не вписані окремо: інакше перша ж правка одного
 * рядка зробить із фікстури набір цифр, які суперечать одна одній, — і тест
 * закріпить саме цю суперечність.
 */
export function basket(deliveryId: string = DELIVERY[0]!.id): Basket {
  const option = DELIVERY.find((o) => o.id === deliveryId) ?? DELIVERY[0]!;
  const topUp =
    option.threshold === null
      ? null
      : {
          threshold: option.threshold,
          saving: option.cost - DELIVERY_AFTER,
          items: TOPUP_ITEMS,
        };
  return {
    runId: "e2e",
    lines: LINES,
    planNote: null,
    shelfNote: null,
    agentTarget: null,
    textIgnored: [],
    total: TOTAL,
    baseTotal: BASE_TOTAL,
    deliveryCost: option.cost,
    totalWeightKg: round(
      buying.reduce((sum, l) => sum + l.qty * (l.weightKg ?? 0), 0),
    ),
    topUp,
    blockers: [],
    slot: {
      start: "2026-08-14T11:00:00+03:00",
      end: "2026-08-14T13:00:00+03:00",
      note: "перший вільний із 7 у 20 найближчих",
    },
    checkoutWebLink: null,
    trace: TRACE,
    feedback: { changes: "approvedChanges", contacts: "call" },
    unresolved: [],
    declined: [],
    questions: [],
    notCollected: [],
    budget: null,
    trimmed: [],
    postponed: [],
    fillNote: null,
    cyclesNote:
      "за циклом я добираю тільки те, що ти береш рівно: таких видів 9 з 10. " +
      "Решту ти береш нерівно — вгадувати не буду, напиши, що треба",
    stats: {
      receipts: 40,
      orders: 12,
      cycled: 63,
      mcpCalls: 14,
      durationMs: TRACE.reduce((sum, s) => sum + (s.durationMs ?? 0), 0),
      costUsd: 0,
      tokensIn: 6410,
      tokensOut: 1562,
      tokensCached: 4704,
      model: "Mistral Large 3",
    },
  };
}

export const POSTPONED: Postponed[] = [
  {
    intent: "Кава Lavazza Crema e Gusto",
    reason: "закінчилось, але не влізло в звичний розмір кошика (14 поз.)",
    estimate: 245,
    refillable: true,
  },
  {
    intent: "Порошок Persil",
    reason: "закінчилось, але не влізло в звичний розмір кошика (14 поз.)",
    estimate: 320,
    refillable: true,
  },
  {
    intent: "Печиво вівсяне",
    reason: "закінчилось, але не влізло в звичний розмір кошика (14 поз.)",
    estimate: null,
    refillable: true,
  },
  {
    intent: "йогурт",
    reason: "двоякий намір понад стелю 3 питань — спитаю наступним прогоном",
    estimate: null,
    refillable: false,
  },
  {
    intent: "Морозиво Хрещатик пломбір",
    reason: "давно не брав, але на цей слот у «Сільпо» його не знайшлось",
    estimate: 119,
    refillable: false,
  },
];

/** Чим добір закриває відкладене: справжні рядки, а не назви намірів.
 *
 * `consideredTotal: 1`, а не нуль: добір іде тим самим `build_lines`, що й
 * збірка, і обраний товар завжди приходить З ПЕРЕЛІКУ — тобто кандидат є
 * щонайменше один. Нуль тут означав би «агент цей рядок не обирав», а таких
 * рядків лише два види: напій, названий гостем у барі, і прогони до того, як
 * відкинуті кандидати взагалі почали писатись (#72).
 */
const REFILLED: CartLine[] = [
  {
    externalProductId: "demo-oat-cookies",
    name: "Печиво вівсяне Богуславна 250 г",
    qty: 1,
    unit: "шт",
    step: null,
    price: 48.9,
    basePrice: null,
    saleNote: null,
    weightKg: 0.25,
    imageUrl: null,
    cardUrl: null,
    reason: "cycle",
    explanation: "закінчилось за циклом — докинув на твоє прохання",
    explanationDetail: null,
    confidence: 0.81,
    atRisk: false,
    needsApproval: false,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
  {
    externalProductId: "demo-coffee-lavazza",
    name: "Кава Lavazza Crema e Gusto 250 г",
    qty: 1,
    unit: "шт",
    step: null,
    price: 249.9,
    basePrice: null,
    saleNote: null,
    weightKg: 0.25,
    imageUrl: null,
    cardUrl: null,
    reason: "cycle",
    explanation: "закінчилось за циклом — докинув на твоє прохання",
    explanationDetail: null,
    confidence: 0.88,
    atRisk: false,
    needsApproval: false,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
  {
    externalProductId: "demo-persil",
    name: "Порошок Persil Color 1,95 кг",
    qty: 1,
    unit: "шт",
    step: null,
    price: 329,
    basePrice: null,
    saleNote: null,
    weightKg: 1.95,
    imageUrl: null,
    cardUrl: null,
    reason: "cycle",
    explanation: "закінчилось за циклом — докинув на твоє прохання",
    explanationDetail: null,
    confidence: 0.86,
    atRisk: false,
    needsApproval: false,
    chain: [],
    mandate: null,
    mandateAhead: false,
    decided: false,
    swapFork: null,
    considered: [],
    consideredTotal: 1,
    sliced: false,
    slicingNote: null,
    cheaper: null,
  },
];

/**
 * Кошик після погодження замін (#77).
 *
 * Міняється рівно текст мандата правлених рядків: ланцюжок не чіпає ні
 * складу, ні цін, ні слота, ні ваги. Саме тому фікстура НЕ вдає прогону —
 * якби вона перераховувала числа, тест зеленів би на тому, чого сервер не
 * робить, і «перезбірки не було» лишалось би недоведеним.
 */
export function swapped(
  before: Basket,
  swaps: { externalProductId: string; policy: string; chain: string[] }[],
  seq: number,
): Basket {
  const byLine = new Map(swaps.map((swap) => [swap.externalProductId, swap]));
  const lines = before.lines.map((line) => {
    const decision = byLine.get(line.externalProductId);
    if (!decision) return line;
    if (decision.policy === "call") {
      return { ...line, mandate: null, needsApproval: true };
    }
    if (decision.policy === "skip") {
      return {
        ...line,
        mandate: "заміни не підбирати, інакше не брати",
        needsApproval: false,
      };
    }
    if (decision.chain.length === 0) return line;
    const names = decision.chain.map(
      (article) =>
        SWAP_OPTIONS.find((option) => option.externalProductId === article)
          ?.name ??
        line.chain.find((link) => link.externalProductId === article)?.name ??
        article,
    );
    return {
      ...line,
      chain: decision.chain.map((article, index) => ({
        externalProductId: article,
        name: names[index] ?? article,
        source: "manual",
        price: null,
        ratio: null,
        byWeight: false,
      })),
      mandate: `якщо немає — ${names.join(", потім ")}, інакше не брати`,
      needsApproval: false,
    };
  });
  return {
    ...before,
    runId: `e2e-swaps-${seq}`,
    lines,
    trace: [
      ...before.trace,
      {
        id: `step-swaps-${seq}`,
        seq: before.trace.length,
        tool: "agent.swaps",
        args: {},
        durationMs: 3,
        calls: null,
        tokensIn: null,
        tokensOut: null,
        resultSummary: `погоджені заміни: ${swaps.length} з ${before.lines.length} рядків`,
        decision: "мандат перерахований без перезбірки",
        tag: "рішення гостя",
        tagTone: "good" as const,
        externalProductId: null,
        prompt: null,
        question: null,
      },
    ],
  };
}

/**
 * Кошик після добору: рядки долились у наявний план, числа перераховані,
 * добране зникло з відкладеного. Повна перезбірка тут була б іншою дією —
 * вона мала б право перевибрати вже обране.
 */
export function refilled(
  before: Basket,
  intents: string[],
  seq: number,
  answers: { intent: string }[] = [],
  keepQuestions = false,
): Basket {
  const byWords = intents.length > 0 || answers.length > 0;
  const here = new Set(before.lines.map((line) => line.externalProductId));
  const added = (byWords ? REFILLED.slice(0, 1) : REFILLED).filter(
    (line) => !here.has(line.externalProductId),
  );
  const lines = [...before.lines, ...added];
  const left = lines.filter((line) => line.reason !== "at_home");
  const total = round(left.reduce((sum, l) => sum + l.qty * l.price, 0));
  const said = new Set(answers.map((answer) => answer.intent));
  return {
    ...before,
    runId: `e2e-${seq}`,
    lines,
    questions: keepQuestions
      ? before.questions
      : before.questions.filter((question) => !said.has(question.intent)),
    total,
    totalWeightKg: round(
      left.reduce((sum, l) => sum + l.qty * (l.weightKg ?? 0), 0),
    ),
    postponed: byWords
      ? before.postponed
      : before.postponed.filter((item) => !item.refillable),
    trace: [
      ...before.trace,
      {
        id: "step-refill-history",
        seq: before.trace.length + 1,
        tool: "silpo_get_my_offline_orders",
        args: { намірів: added.length },
        durationMs: 900,
        calls: null,
        tokensIn: null,
        tokensOut: null,
        resultSummary: "40 чеків перечитано під добір",
        decision: "історія читається наново: план тримає рядки, а не чеки",
        tag: null,
        tagTone: "muted",
        externalProductId: null,
        prompt: null,
        question: null,
      },
      {
        id: "step-refill-search",
        seq: before.trace.length + 2,
        tool: "silpo_find_products_batch",
        args: { queries: added.length },
        durationMs: 400,
        calls: null,
        tokensIn: null,
        tokensOut: null,
        resultSummary: `кандидатів: ${added.length * 3} на ${added.length} намірів`,
        decision: null,
        tag: null,
        tagTone: "muted",
        externalProductId: null,
        prompt: null,
        question: null,
      },
      {
        id: "step-refill",
        seq: before.trace.length + 3,
        tool: "Mistral Large 3",
        args: { додано: added.length },
        durationMs: 4200,
        calls: null,
        tokensIn: null,
        tokensOut: null,
        resultSummary: `добір: ${added.map((line) => line.name).join(", ")}`,
        decision: `докинуто ${added.length} поз.; разом ${total} грн`,
        tag: `+${added.length} поз.`,
        tagTone: "good",
        externalProductId: null,
        prompt: "pick[head@0e82ff24,label@7d9d6d22,tail@83ac1de5]",
        question: null,
      },
    ],
  };
}

/**
 * Вхід Б: той самий кошик, але ПРОЧИТАНИЙ, а не зібраний.
 *
 * Різниця, заради якої вхід існує, показується одним рядком: звичного сиру на
 * полиці немає, і замість реактивної кнопки «Замінити» їде перша ланка
 * ПОГОДЖЕНОГО ланцюжка.
 */
export function cartBasket(deliveryId?: string): Basket {
  const base = basket(deliveryId);
  let swapped: string | null = null;
  const lines = base.lines.map((line) => {
    const link = line.chain[0];
    if (line.externalProductId !== "demo-cheese" || !link) return line;
    swapped = link.name;
    return {
      ...line,
      externalProductId: link.externalProductId,
      name: link.name,
      reason: "substituted" as const,
      explanation: `звичного не було — поклав погоджену заміну №1: ${link.name}`,
      explanationDetail:
        "Ланцюжок погоджений ДО того, як товар зник з полиці, тому дзвінок " +
        "збирача не потрібен, а рядок не лишився діркою.",
      chain: [],
      mandate: null,
      mandateAhead: false,
      decided: false,
      swapFork: null,
      atRisk: false,
      needsApproval: false,
    };
  });
  const steps: TraceStep[] = [
    {
      id: "step-cart",
      seq: 0,
      tool: "get_shopping_cart_by_id",
      args: {},
      durationMs: 300,
      calls: null,
      tokensIn: null,
      tokensOut: null,
      resultSummary: `чужий кошик прочитано: ${base.lines.length} рядків`,
      decision:
        "хто наповнив кошик — не має значення: кошик і є API між продуктами",
      tag: "вхід Б",
      tagTone: "good",
      externalProductId: null,
      prompt: null,
      question: null,
    },
    ...base.trace,
    {
      id: "step-revalidate",
      seq: 0,
      tool: "core.revalidation",
      args: { рядків: base.lines.length, проблемних: swapped ? 1 : 0 },
      durationMs: 200,
      calls: null,
      tokensIn: null,
      tokensOut: null,
      resultSummary: swapped
        ? `звичного не було — поклав погоджену заміну №1: ${swapped}`
        : "усі рядки доступні на момент слота",
      decision: "рішення прийняте наперед, а не питається зараз",
      tag: swapped ? "замін 1" : null,
      tagTone: "good",
      externalProductId: null,
      prompt: null,
      question: null,
    },
  ];
  return {
    ...base,
    lines,
    cyclesNote:
      "цей кошик наповнив хтось інший — за циклом я до нього нічого не добираю",
    trace: steps.map((step, index) => ({ ...step, seq: index + 1 })),
  };
}

export const PANTRY: PantryItem[] = [
  {
    wanted: false,
    mandate: null,
    writtenAs: ["Рис довгозернистий"],
    parts: [],
    group: null,
    id: "rice",
    aisle: "Бакалія і консерви",
    label: "Рис",
    qty: 2,
    usualQty: 3,
    unit: "уп",
    leftRatio: 0.63,
    daysLeft: 12,
    cycleDays: 19,
    cycleSaid: false,
    named: true,
    state: "оцінка: брав 7 дн тому · цикл ~19 дн",
    keeps: null,
    sanity: "рис витрачають рівно, пачки вистачає надовго",
    trust: "",
    ask: false,
    runningOut: false,
    imageUrl: null,
    source: "receipts",
    promo: null,
    arrived: "приїхало вчора",
    usual: {
      externalProductId: "demo-rice",
      name: "Преміа довгозернистий 800 г",
      share: "6 з 7",
      price: 54.9,
      unit: "уп",
      pack: "",
    },
  },
  {
    wanted: false,
    mandate: null,
    writtenAs: [],
    parts: [
      {
        label: "Папір туалетний Zewa Deluxe 8 рулонів",
        unit: "уп",
        receipts: 9,
        daysSince: 9,
        fresh: true,
      },
    ],
    group: null,
    id: "paper",
    aisle: "Для дому",
    label: "Туалетний папір",
    qty: 6,
    usualQty: 12,
    unit: "рул",
    leftRatio: 0.5,
    daysLeft: 9,
    cycleDays: 18,
    cycleSaid: false,
    named: true,
    state: "оцінка: брав 9 дн тому · цикл ~18 дн",
    keeps: null,
    sanity:
      "паперові рушники витрачають рівномірно, але запаси поповнюють великими партіями",
    trust: "",
    ask: true,
    runningOut: false,
    imageUrl: null,
    source: "receipts",
    promo: "береш по акції: 9 з 10, зазвичай по 12",
    arrived: null,
    usual: {
      externalProductId: "demo-paper",
      name: "Zewa 8 рулонів",
      share: "9 з 10",
      price: 189,
      unit: "уп",
      pack: "",
    },
  },
  {
    wanted: false,
    mandate: null,
    writtenAs: [],
    parts: [],
    group: null,
    id: "olive-oil",
    aisle: "Бакалія і консерви",
    label: "Олія оливкова",
    qty: null,
    usualQty: 1,
    unit: "шт",
    leftRatio: 0.08,
    daysLeft: 1,
    cycleDays: 12,
    cycleSaid: false,
    named: true,
    state: "оцінка: брав 11 дн тому · цикл ~12 дн",
    keeps: null,
    sanity: null,
    trust: "",
    ask: false,
    runningOut: false,
    imageUrl: null,
    source: "receipts",
    promo: null,
    arrived: null,
    usual: {
      externalProductId: "demo-oil",
      name: "Monini 0,5 л",
      share: "4 з 5",
      price: 279,
      unit: "шт",
      pack: "",
    },
  },
  {
    wanted: false,
    mandate: null,
    writtenAs: [],
    parts: [],
    group: null,
    id: "salt",
    aisle: "Соуси і спеції",
    label: "Сіль",
    qty: null,
    usualQty: 1,
    unit: "уп",
    leftRatio: 0.93,
    daysLeft: 84,
    cycleDays: 90,
    cycleSaid: false,
    named: true,
    state: "оцінка: брав 6 дн тому · цикл ~90 дн",
    keeps: null,
    sanity: "сіль витрачають рівно, але пачка стоїть роками",
    trust: "",
    ask: true,
    runningOut: false,
    imageUrl: null,
    source: "receipts",
    promo: null,
    arrived: null,
    usual: {
      externalProductId: "demo-salt",
      name: "Морська дрібна 1 кг",
      share: "3 з 3",
      price: 34.9,
      unit: "уп",
      pack: "",
    },
  },
  {
    wanted: false,
    mandate: null,
    writtenAs: [],
    parts: [],
    group: null,
    id: "pasta",
    aisle: "Бакалія і консерви",
    label: "Паста",
    qty: 3,
    usualQty: 4,
    unit: "уп",
    leftRatio: 0.72,
    daysLeft: 18,
    cycleDays: 25,
    cycleSaid: false,
    named: true,
    state: "оцінка: брав 7 дн тому · цикл ~25 дн",
    keeps: null,
    sanity: "пасту беруть про запас: пачки лежать до нагоди",
    trust: "",
    ask: true,
    runningOut: false,
    imageUrl: null,
    source: "receipts",
    promo: null,
    arrived: null,
    usual: {
      externalProductId: "demo-pasta",
      name: "Barilla пенне 500 г",
      share: "8 з 11",
      price: 74.9,
      unit: "уп",
      pack: "",
    },
  },
  {
    wanted: false,
    mandate: null,
    writtenAs: [],
    parts: [
      {
        label: "Активіа питна 290 г",
        unit: "шт",
        receipts: 7,
        daysSince: 11,
        fresh: true,
      },
    ],
    group: null,
    id: "yogurt",
    aisle: "Молочні продукти та яйця",
    label: "Йогурт питний",
    qty: 0,
    usualQty: 4,
    unit: "шт",
    leftRatio: 0,
    daysLeft: 0,
    cycleDays: 8,
    cycleSaid: false,
    named: true,
    state: "оцінка: брав 11 дн тому · цикл ~8 дн — мабуть, закінчилось",
    keeps: null,
    sanity: "йогурт п'ють нерівно -- то щодня, то через тиждень",
    trust: "",
    ask: true,
    runningOut: true,
    imageUrl: null,
    source: "receipts",
    promo: null,
    arrived: null,
    usual: {
      externalProductId: "demo-yogurt",
      name: "Активіа питна 290 г",
      share: "7 з 9",
      price: 39.9,
      unit: "шт",
      pack: "",
    },
  },
  {
    wanted: false,
    mandate: null,
    writtenAs: [],
    parts: [],
    group: null,
    id: "fillet",
    aisle: "М'ясо",
    label: "Філе куряче",
    qty: 0,
    usualQty: 0.6,
    unit: "кг",
    leftRatio: 0,
    daysLeft: 0,
    cycleDays: 7,
    cycleSaid: false,
    named: true,
    state: "оцінка: брав 9 дн тому · цикл ~7 дн — мабуть, закінчилось",
    keeps: null,
    sanity: null,
    trust: "",
    ask: false,
    runningOut: true,
    imageUrl: null,
    source: "receipts",
    promo: null,
    arrived: null,
    usual: {
      externalProductId: "demo-fillet",
      name: "Наша Ряба філе охолоджене",
      share: "6 з 8",
      price: 219,
      unit: "кг",
      pack: "",
    },
  },
  {
    wanted: false,
    mandate: null,
    writtenAs: [],
    parts: [],
    group: null,
    id: "ice-cream",
    aisle: "Заморожена продукція",
    label: "Морозиво",
    qty: null,
    usualQty: 1,
    unit: "шт",
    leftRatio: 0,
    daysLeft: 0,
    cycleDays: 32,
    cycleSaid: false,
    named: true,
    state: "оцінка: давно не брав: 76 дн при звичних ~32",
    keeps: null,
    sanity: null,
    trust: "",
    ask: false,
    runningOut: true,
    imageUrl: null,
    source: "receipts",
    promo: null,
    arrived: null,
    usual: {
      externalProductId: "demo-ice",
      name: "Рудь пломбір 500 г",
      share: "3 з 4",
      price: 119,
      unit: "шт",
      pack: "",
    },
  },
  {
    wanted: false,
    mandate: null,
    writtenAs: [],
    parts: [],
    group: null,
    id: "ketchup",
    aisle: "Соуси і спеції",
    label: "Кетчуп",
    qty: null,
    usualQty: 1,
    unit: "шт",
    leftRatio: null,
    daysLeft: null,
    cycleDays: null,
    cycleSaid: false,
    named: true,
    state:
      "оцінка: береш нерівно: між покупками від 2 до 68 дн, остання 10 дн тому",
    keeps: null,
    sanity: null,
    trust: "",
    ask: false,
    runningOut: false,
    imageUrl: null,
    source: "receipts",
    promo: null,
    arrived: null,
    usual: null,
  },
  {
    wanted: false,
    mandate: null,
    writtenAs: [],
    parts: [],
    group: null,
    id: "tuna",
    aisle: "Бакалія і консерви",
    label: "Тунець консервований",
    qty: null,
    usualQty: 1,
    unit: "шт",
    leftRatio: 0,
    daysLeft: 0,
    cycleDays: 14,
    cycleSaid: false,
    named: true,
    state: "оцінка: брав 21 дн тому · цикл ~14 дн — мабуть, закінчилось",
    keeps: null,
    sanity: null,
    trust: "",
    ask: false,
    runningOut: true,
    imageUrl: null,
    source: "receipts",
    promo: null,
    arrived: null,
    usual: {
      externalProductId: "demo-tuna",
      name: "Aquamarine у власному соку",
      share: "5 з 6",
      price: 89.9,
      unit: "шт",
      pack: "",
    },
  },
];

function marked(
  item: PantryItem,
  action: "bought" | "qty",
  said: number,
): PantryItem {
  const cycle = item.cycleDays ?? 0;
  const step = item.unit === "кг" || item.unit === "л" ? 0.1 : 1;
  const usual = item.usualQty ?? 0;
  const share =
    action === "bought" || usual <= 0 ? 1 : Math.max(0, said / usual);
  const since = Math.round(cycle * (1 - share));
  const runningOut = since >= cycle;
  const ratio = runningOut ? 0 : 1 - since / cycle;
  const qty =
    usual <= step && ratio <= 1
      ? null
      : Math.max(
          step,
          Math.round(Math.round((usual * ratio) / step) * step * 100) / 100,
        );
  const word =
    since === 0
      ? "взято сьогодні"
      : qty !== null
        ? `удома ~${uaNumber(qty)} ${item.unit}`
        : "це вже є";
  const daysLeft = runningOut ? 0 : cycle - since;
  return {
    ...item,
    qty: runningOut ? 0 : qty,
    runningOut,
    leftRatio: ratio,
    daysLeft,
    state: `${word} · ${daysLeft > cycle ? "запас понад цикл" : "цикл"} ~${cycle} дн`,
  };
}

function retimed(item: PantryItem, days: number, since: number): PantryItem {
  const runningOut = since >= days;
  const ratio = runningOut ? 0 : 1 - since / days;
  const step = item.unit === "кг" || item.unit === "л" ? 0.1 : 1;
  const usual = item.usualQty ?? 0;
  const qty =
    usual <= step && ratio <= 1
      ? null
      : runningOut
        ? 0
        : Math.max(
            step,
            Math.round(Math.round((usual * ratio) / step) * step * 100) / 100,
          );
  return {
    ...item,
    cycleDays: days,
    cycleSaid: true,
    named: true,
    qty,
    leftRatio: ratio,
    daysLeft: runningOut ? 0 : days - since,
    runningOut,
    state:
      `вистачає на ~${days} дн · брав ${since} дн тому` +
      (runningOut ? " — мабуть, закінчилось" : ""),
  };
}

/** Скільки днів тому це брали ЗА ЧЕКОМ — те, чого слово про цикл не міняє. */
function sinceOf(item: PantryItem): number {
  if (item.cycleDays === null) return DEFAULT_SINCE;
  return Math.round(item.cycleDays * (1 - (item.leftRatio ?? 0)));
}

const DEFAULT_SINCE = 10;

/** «0,2» — число в тексті стану, як його друкує сервер. */
function uaNumber(value: number): string {
  return String(Math.round(value * 100) / 100).replace(".", ",");
}

export const LONG_PANTRY: PantryItem[] = [
  ...PANTRY,
  ...Array.from({ length: 33 }, (_, i) => ({
    writtenAs: [],
    parts: [],
    wanted: false,
    mandate: null,
    id: `kind-${i}`,
    label: `Запас ${i + 1}`,
    aisle: i % 2 === 0 ? "Бакалія і консерви" : "Для дому",
    group: null,
    qty: null,
    usualQty: 1,
    unit: "уп",
    leftRatio: 0.5,
    daysLeft: 10 + i,
    cycleDays: 30,
    cycleSaid: false,
    named: true,
    state: `оцінка: брав ${i + 1} дн тому · цикл ~30 дн`,
    keeps: null,
    sanity: null,
    trust: "",
    ask: false,
    runningOut: false,
    imageUrl: null,
    source: "receipts" as const,
    promo: null,
    arrived: null,
    usual: null,
  })),
];

/** Відділ, у якому рядків PANTRY більше одного -- ним і міряється «рейки немає». */
const ONE_AISLE = "Бакалія і консерви";

export const TWIN_PANTRY: PantryItem[] = [
  ...PANTRY,
  {
    wanted: false,
    mandate: null,
    writtenAs: [],
    parts: [
      {
        label: "Сир Комо Гауда 45%",
        unit: "кг",
        receipts: 4,
        daysSince: 9,
        fresh: true,
      },
      {
        label: "Сир Президент Маасдам",
        unit: "кг",
        receipts: 2,
        daysSince: 210,
        fresh: false,
      },
    ],
    group: "сир",
    id: "cheese-hard",
    aisle: "Сири",
    label: "сир · твердий",
    qty: null,
    usualQty: 1,
    unit: "шт",
    leftRatio: 0,
    daysLeft: 0,
    cycleDays: 6,
    cycleSaid: false,
    named: true,
    state: "оцінка: брав 9 дн тому · цикл ~6 дн — мабуть, закінчилось",
    keeps: null,
    sanity: null,
    trust: "",
    ask: false,
    runningOut: true,
    imageUrl: null,
    source: "receipts",
    promo: null,
    arrived: null,
    usual: null,
  },
  {
    wanted: false,
    mandate: null,
    writtenAs: [],
    parts: [
      {
        label: "Сир Президент Крем-Чіз",
        unit: "шт",
        receipts: 3,
        daysSince: 6,
        fresh: true,
      },
      {
        label: "Сир Альметте вершковий",
        unit: "шт",
        receipts: 2,
        daysSince: 40,
        fresh: false,
      },
    ],
    group: "сир",
    id: "cheese-cream",
    aisle: "Сири",
    label: "сир · вершковий",
    qty: null,
    usualQty: 1,
    unit: "шт",
    leftRatio: 0.7,
    daysLeft: 7,
    cycleDays: 21,
    cycleSaid: false,
    named: true,
    state: "оцінка: брав 6 дн тому · цикл ~21 дн",
    keeps: null,
    sanity: null,
    trust: "",
    ask: false,
    runningOut: false,
    imageUrl: null,
    source: "receipts",
    promo: null,
    arrived: null,
    usual: null,
  },
];

const REFILL_MS = 400;

const PANTRY_WRITE_MS = 1200;

/** Види, які гість попросив не показувати (#124). Стан, як у базі. */
const hidden_kinds = new Set<string>();

/** Наміри, згортання яких гість заперечив (#335). Теж стан, а не фільтр. */
const split_intents = new Set<string>();

/** Який набір рядків показує цей стенд. Один вибір на два шляхи -- читання
 *  і правку: два вибори розійшлись би першою ж новою фікстурою. */
function pantryRows(kind: MockOptions["pantry"]): PantryItem[] {
  if (kind === "long") return LONG_PANTRY;
  if (kind === "twins") return TWIN_PANTRY;
  if (kind === "one-aisle")
    return PANTRY.filter((item) => item.aisle === ONE_AISLE);
  return PANTRY;
}

/** Рядки без схованих -- саме так відповідає сервер. */
function shownOnly(rows: PantryItem[]): PantryItem[] {
  return rows.filter((item) => !hidden_kinds.has(item.id));
}

function listedIn(rows: PantryItem[], labels: Set<string>): PantryItem[] {
  return rows.map((item) =>
    labels.has(item.label) ? { ...item, wanted: true } : item,
  );
}

function apartOf(rows: PantryItem[]): PantryItem[] {
  return rows.map((item) =>
    item.group !== null && split_intents.has(item.group)
      ? { ...item, group: null }
      : item,
  );
}

/** Підписи схованого: число без переліку не дає зняти ігнор. */
function hiddenNow(base: PantryItem[]): {
  receipts: number;
  kinds: number;
  hidden: string[];
} {
  return {
    receipts: 118,
    kinds: 143,
    hidden: base
      .filter((item) => hidden_kinds.has(item.id))
      .map((item) => item.label),
  };
}

const PANTRY_TRACE: TraceStep[] = [
  {
    id: "step-pantry-read",
    seq: 1,
    tool: "silpo_get_my_offline_orders",
    args: {
      чеків: 118,
      "зі сховища": 115,
      "дочитано наживо": 3,
      замовлень: 67,
    },
    durationMs: 812,
    calls: null,
    tokensIn: null,
    tokensOut: null,
    resultSummary: "118 чеків і 67 замовлень; зі сховища 115, дочитано 3",
    decision: "історія зберігається, тож щоразу дочитується лише хвіст",
    tag: null,
    tagTone: "muted",
    externalProductId: null,
    prompt: null,
    question: null,
  },
  {
    id: "step-pantry-names",
    seq: 2,
    tool: "кеш назв",
    args: { видів: 143, "з кешу": 143, спитано: 0, "без назви": 0 },
    durationMs: 12,
    calls: 2,
    tokensIn: 9314,
    tokensOut: 708,
    resultSummary: "видів 143: з кешу 143, спитано 0, без назви 0",
    decision: "назва -- властивість ТОВАРУ, не гостя: кеш вічний і спільний",
    tag: null,
    tagTone: "muted",
    externalProductId: null,
    prompt: null,
    question: null,
  },
  {
    id: "step-pantry-rows",
    seq: 3,
    tool: "core.cycles",
    args: {
      рядків: 44,
      "зі смугою": 12,
      "без циклу": 32,
      позначок: 2,
      "названих циклів": 1,
      сховано: 0,
      дописано: 1,
    },
    durationMs: null,
    calls: null,
    tokensIn: null,
    tokensOut: null,
    resultSummary:
      "рядків 44: зі смугою 12, без циклу 32; слів гостя накладено 4",
    decision:
      "рядок без доведеного циклу лишається, але без смуги і без «закінчилось»",
    tag: null,
    tagTone: "muted",
    externalProductId: null,
    prompt: null,
    question: null,
  },
  {
    id: "step-batch",
    seq: 1,
    tool: "model",
    args: { планувала: ["pantry.name"], виконано: ["pantry.name"] },
    durationMs: null,
    calls: null,
    tokensIn: null,
    tokensOut: null,
    resultSummary: "оберт 1: планувала 1, виконала 1, нового дізналась 1",
    decision: null,
    tag: "+1",
    tagTone: "good",
    externalProductId: null,
    prompt: null,
    question: null,
  },
  {
    id: "step-batch",
    seq: 2,
    tool: "model",
    args: { планувала: ["pantry.rhythm"], виконано: ["pantry.rhythm"] },
    durationMs: null,
    calls: null,
    tokensIn: null,
    tokensOut: null,
    resultSummary: "оберт 2: планувала 1, виконала 1, нового дізналась 1",
    decision: null,
    tag: "+1",
    tagTone: "good",
    externalProductId: null,
    prompt: null,
    question: null,
  },
];

function folded(items: PantryItem[]): PantryItem[] {
  const runs = new Map<string | PantryItem, PantryItem[]>();
  for (const item of items) {
    const key = item.group ?? item;
    const run = runs.get(key);
    if (run) run.push(item);
    else runs.set(key, [item]);
  }
  return [...runs.values()].flat();
}

function aislesOf(items: PantryItem[]): { title: string; rows: number }[] {
  const rows = new Map<string, number>();
  for (const item of items) {
    if (item.aisle === null) continue;
    rows.set(item.aisle, (rows.get(item.aisle) ?? 0) + 1);
  }
  return [...rows.entries()].map(([title, n]) => ({ title, rows: n }));
}

let lastDrawn: Pantry | null = null;
let runsMade = 0;

function pantryState(
  items: PantryItem[],
  counted: {
    receipts: number;
    kinds: number;
    orders?: number;
    source?: "receipts" | "manual";
    unlisted?: number;
    hidden?: string[];
    apart?: string[];
    atBar?: string[];
    outside?: string[];
    spend?: SpendTarget;
    targetPool?: number;
    targetEstimate?: number | null;
    tripGap?: number;
    listLimit?: number;
    trace?: TraceStep[];
  } = {
    receipts: 118,
    kinds: 143,
  },
): Pantry {
  const manual = items.filter((item) => item.source === "manual");
  const counted_rows = items.filter((item) => item.source !== "manual");
  const out = counted_rows.filter((item) => item.runningOut);
  const shown = folded([
    ...out,
    ...manual,
    ...counted_rows.filter((item) => !item.runningOut),
  ]);
  const drawn = {
    items: shown,
    refined: null,
    asked: [],
    fresh: true,
    aisles: aislesOf(shown),
    ...counted,
    changed: null,
    orders: counted.orders ?? 0,
    trackedFrom: 3,
    spend: counted.spend ?? SPEND,
    source: counted.source ?? "receipts",
    unlisted: counted.unlisted ?? 0,
    outside: counted.outside ?? UNTRACKED,
    hidden: counted.hidden ?? [],
    atBar: counted.atBar ?? [],
    apart: counted.apart ?? [],
    trace: counted.trace ?? PANTRY_TRACE,
    targetPool: counted.targetPool ?? priced_rows(counted_rows).length,
    targetEstimate:
      counted.targetEstimate !== undefined
        ? counted.targetEstimate
        : poolEstimate(counted_rows),
    tripGap: counted.tripGap ?? 3,
    listLimit: counted.listLimit ?? 14,
    spent: null,
  };
  lastDrawn = drawn;
  return drawn;
}

/** Рядки, за якими стоїть ціна з чеків: без неї добирати ними нема чим. */
function priced_rows(rows: PantryItem[]): PantryItem[] {
  return rows.filter((item) => item.usual !== null && item.usual.price > 0);
}

/** На скільки тягне пул. `null` — пул порожній, і суми немає, а не нуль (#76). */
function poolEstimate(rows: PantryItem[]): number | null {
  const priced = priced_rows(rows);
  if (priced.length === 0) return null;
  return round(
    priced.reduce(
      (sum, item) => sum + (item.usual?.price ?? 0) * (item.usualQty ?? 1),
      0,
    ),
  );
}

export const SWAP_OPTIONS: SwapOption[] = [
  {
    externalProductId: "demo-polyana",
    name: "Поляна Квасова 0,5 л",
    price: 39.9,
    ratio: "0,5л",
    stock: 12,
    available: true,
    imageUrl: null,
    cardUrl: "https://silpo.ua/product/voda-polyana-kvasova-0-5-l-123456",
    sameKind: true,
    kind: "Вода мінеральна",
    sliced: false,
    byWeight: false,
  },
  {
    externalProductId: "demo-morshynska",
    name: "Моршинська сильногазована 1,5 л",
    price: 27.5,
    ratio: "1,5л",
    stock: 40,
    available: true,
    imageUrl: null,
    cardUrl: "https://silpo.ua/product/voda-morshynska-1-5-l-654321",
    sameKind: true,
    kind: "Вода мінеральна",
    sliced: false,
    byWeight: false,
  },
  {
    externalProductId: "demo-borjomi",
    name: "Боржомі 0,33 л",
    price: 59.9,
    ratio: "0,33л",
    stock: 4,
    available: true,
    imageUrl:
      "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
    cardUrl: null,
    sameKind: true,
    kind: "Вода мінеральна",
    sliced: false,
    byWeight: false,
  },
  {
    externalProductId: "demo-bread-tost",
    name: "Хліб Київський тостовий нарізаний",
    price: 38.84,
    ratio: "400г",
    stock: 25,
    available: true,
    imageUrl: null,
    cardUrl: null,
    sameKind: true,
    kind: "Хліб",
    sliced: true,
    byWeight: false,
  },
  {
    externalProductId: "demo-mivina",
    name: "Вермішель Мівіна з куркою 59,2 г",
    price: 21.9,
    ratio: "59,2г",
    stock: 60,
    available: true,
    imageUrl: null,
    cardUrl: null,
    sameKind: false,
    kind: "Вода мінеральна",
    sliced: false,
    byWeight: false,
  },
];

function withSwaps(
  built: Basket,
  swaps: { externalProductId: string; policy: string; chain: string[] }[],
): Basket {
  if (swaps.length === 0) return built;
  const known = new Map(
    SWAP_OPTIONS.map((option) => [option.externalProductId, option.name]),
  );
  const decisions = new Map(
    swaps.map((swap) => [swap.externalProductId, swap]),
  );
  const lines = built.lines.map((line) => {
    const decision = decisions.get(line.externalProductId);
    if (!decision) return line;
    const chain = decision.chain.map((id) => ({
      externalProductId: id,
      name:
        known.get(id) ??
        line.chain.find((sub) => sub.externalProductId === id)?.name ??
        id,
      source: "manual" as const,
      price: null,
      ratio: null,
      byWeight: false,
    }));
    const mandate =
      chain.length > 0
        ? `${line.name}: якщо немає — ${chain.map((sub) => sub.name).join(", потім ")}. Не дзвонити.`
        : line.mandate;
    return { ...line, chain, mandate, needsApproval: false };
  });
  return { ...built, lines };
}

const AUTO_FORK: PriceFork = { low: 31.41, high: 38.39, per: "" };

const AUTO_FORK_SAID = "31,41–38,39";

/**
 * Стан із вилкою -- і він ЕКСПОРТОВАНИЙ, бо той самий кошик потрібен тесту
 * з іншого боку (#352): «усі мандати -- вилки» збирається з ЦЬОГО ж
 * результату зняттям мандатів у сусідів, а не власними числами. Фікстура,
 * яка порахувала б вилку сама, зеленила б розходження, заради якого її
 * рахують один раз (#90).
 */
export function withAutoSwap(built: Basket): Basket {
  const lines = built.lines.map((line) =>
    line.externalProductId === "demo-yogurt"
      ? {
          ...line,
          needsApproval: false,
          explanation: "залишок 3 у твоїй філії",
          swapFork: AUTO_FORK,
          mandate:
            "якщо немає — інший натуральний йогурт без добавок, 260 г " +
            `у межах ${AUTO_FORK_SAID} грн, інакше не брати`,
        }
      : line,
  );
  return { ...built, lines };
}

export const RULES: Exclusion[] = [
  { id: "rule:healthier", label: "здоровіше", permanent: false, active: true },
];

/**
 * Обмеження з профілю «Сільпо». За замовчуванням їх немає — рівно так, як у
 * живого акаунта: `get_my_food_restrictions` віддав `all-food`, тобто
 * «обмежень немає» (виміряно 23.08). Тест, якому потрібне обмеження, просить
 * його явно.
 */
export const PROFILE_RULES: Exclusion[] = [
  {
    id: "profile:lactose-free",
    label: "без лактози",
    permanent: true,
    active: true,
  },
];

const BAR_ITEMS: BarItem[] = [
  {
    id: "vodka",
    label: "Горілка",
    kind: "strong",
    times: 4,
    daysSince: 26,
    usual: {
      externalProductId: "demo-vodka-nemiroff",
      name: "Nemiroff Житня з перцем 0,5 л",
      share: "4 з 4",
      price: 289,
      unit: "шт",
      pack: "0,5л",
    },
    priceFrom: 249,
    priceTo: 339,
    forkNote: "брав 0,5л за 249–339 ₴",
    source: "receipts",
    kindSaid: false,
  },
  {
    id: "whisky",
    label: "Віскі",
    kind: "strong",
    times: 2,
    daysSince: 61,
    usual: {
      externalProductId: "demo-whisky-jameson",
      name: "Jameson 0,7 л",
      share: "2 з 2",
      price: 749,
      unit: "шт",
      pack: "0,7л",
    },
    priceFrom: 649,
    priceTo: 849,
    forkNote: "брав за цю ціну",
    source: "receipts",
    kindSaid: false,
  },
  {
    id: "wine-semisweet",
    label: "Червоне напівсолодке",
    kind: "wine",
    times: 6,
    daysSince: 12,
    usual: {
      externalProductId: "demo-wine-villa",
      name: "Villa UA Троянда 0,75 л",
      share: "5 з 6",
      price: 179,
      unit: "шт",
      pack: "0,75л",
    },
    priceFrom: 149,
    priceTo: 219,
    forkNote: "брав за цю ціну",
    source: "receipts",
    kindSaid: false,
  },
  {
    id: "wine-dry",
    label: "Червоне сухе",
    kind: "wine",
    times: 3,
    daysSince: 34,
    usual: {
      externalProductId: "demo-wine-shabo",
      name: "Shabo Класика Каберне 0,75 л",
      share: "2 з 3",
      price: 219,
      unit: "шт",
      pack: "",
    },
    priceFrom: 189,
    priceTo: 269,
    forkNote: "брав за цю ціну",
    source: "receipts",
    kindSaid: false,
  },
  {
    id: "beer-lager",
    label: "Пиво світле",
    kind: "light",
    times: 9,
    daysSince: 6,
    usual: {
      externalProductId: "demo-beer-lviv",
      name: "Львівське 1715 0,5 л",
      share: "7 з 9",
      price: 42.9,
      unit: "шт",
      pack: "",
    },
    priceFrom: 34,
    priceTo: 52,
    forkNote: "брав за цю ціну",
    source: "receipts",
    kindSaid: false,
  },
  {
    id: "cider",
    label: "Сидр",
    kind: "light",
    times: 2,
    daysSince: 47,
    usual: {
      externalProductId: "demo-cider-somersby",
      name: "Somersby яблучний 0,5 л",
      share: "2 з 2",
      price: 59.9,
      unit: "шт",
      pack: "",
    },
    priceFrom: 49,
    priceTo: 72,
    forkNote: "брав за цю ціну",
    source: "receipts",
    kindSaid: false,
  },
];

/**
 * Види, які гість БЕРЕ, а комора не веде: покупок менше за поріг (#26).
 * Саме вони стоять прикладами у вікні «Додати в комору» -- і саме тому
 * фікстура їх возить: без них e2e зеленив би екран з нашими прикладами
 * там, де сервер дає його власні (клас #34).
 */
export const UNTRACKED = ["Мед акацієвий", "Оцет бальзамічний"];

/** Ціль кошика і пресети з замовлень гостя (#212) -- числа живого заміру 30.08. */
export const SPEND: SpendTarget = {
  target: 1500,
  orders: 94,
  presets: [1200, 1500, 2100, 3300],
  note: "твої замовлення: медіана 1500, p75 2100 — беру 1500",
};

export const BAR: Bar = {
  items: BAR_ITEMS,
  receipts: 48,
  orders: 0,
  kinds: 183,
  named: 45,
  trackedFrom: 3,
  dropped: 0,
  source: "receipts",
  unlisted: 0,
  changed: null,
};

/** Чеки є, види названі, а напоїв серед звичного немає. */
export const BAR_NO_DRINKS: Bar = { ...BAR, items: [] };

/** Модель не відповіла: бар НЕПОРАХОВАНИЙ, а не порожній. */
export const BAR_UNNAMED: Bar = { ...BAR, items: [], named: 0 };

/** Покупок у «Сільпо» не видно взагалі. */
export const BAR_NO_RECEIPTS: Bar = {
  items: [],
  source: "receipts",
  unlisted: 0,
  changed: null,
  receipts: 0,
  orders: 0,
  kinds: 0,
  named: 0,
  trackedFrom: 3,
  dropped: 0,
};

/** Вид зник, бо в чеках немає ні ціни, ні дати -- поріг тут ПРОЙДЕНО (#182). */
export const BAR_DROPPED: Bar = { ...BAR, dropped: 2 };

/** Те саме на порожньому барі: причина четверта, а не «мало покупок». */
export const BAR_ONLY_DROPPED: Bar = { ...BAR, items: [], dropped: 2 };

/** Рекомендована пара плюс хвіст каталогу: селектор перевіряється на
 *  блоках і на ключі, а не на довжині списку. Форма мусить збігатися з тим,
 *  що рахує `core/models.py`, -- фікстура, добріша за сервер, зеленила б
 *  код, який ключа не питає (клас #34). */
export const MODELS: ModelOption[] = [
  {
    id: "mistral.mistral-large-3-675b-instruct",
    label: "Mistral Large 3",
    note: "повільніше, зате безкоштовно — платить проєкт",
    available: true,
    active: true,
    recommended: true,
    needsKey: false,
    supportsFast: true,
    fastByDefault: true,
  },
  {
    id: "gpt-5.6-luna",
    label: "GPT-5.6 Luna",
    note: "швидше, але з твоїм ключем OpenAI",
    available: true,
    active: false,
    recommended: true,
    needsKey: true,
    supportsFast: true,
    fastByDefault: false,
  },
  {
    id: "mistral.devstral-2-123b",
    label: "Devstral 2",
    note: "запасна",
    available: true,
    active: false,
    recommended: false,
    needsKey: false,
    supportsFast: false,
    fastByDefault: false,
  },
  {
    id: "anthropic.claude-opus-5",
    label: "Claude Opus 5",
    note: "доступ на акаунті ще не виданий",
    available: false,
    active: false,
    recommended: false,
    needsKey: false,
    supportsFast: false,
    fastByDefault: false,
  },
];

/** Стан з'єднання підключеного гостя. */
export const SESSION = {
  connected: true,
  expiresAt: "2026-09-14T12:00:00+00:00",
  llmKey: false,
};

/**
 * Кроки, які канал віддає, поки ПЕТЛЯ комори йде (#341).
 *
 * Форма та сама, що в кроків збірки: канал один, і фікстура, яка віддала б
 * тут щось своє, зеленила б екран, що читає неіснуючу форму (клас #34).
 */
const PANTRY_LOOP_STEPS: TraceStep[] = [
  {
    id: "step-pantry-plan",
    seq: 1,
    tool: "model",
    args: { кроків: 4 },
    durationMs: 1_840,
    calls: null,
    tokensIn: null,
    tokensOut: null,
    resultSummary: "план від моделі: назвати види, розсудити ритм",
    decision: null,
    tag: null,
    tagTone: "muted",
    externalProductId: null,
    prompt: null,
    question: null,
  },
  {
    id: "step-pantry-name",
    seq: 1,
    tool: "model",
    args: { кандидатів: 133, "з кешу": 0 },
    durationMs: 26_400,
    calls: 2,
    tokensIn: 9314,
    tokensOut: 708,
    resultSummary: "названо 133 з 133: з кешу 0, спитано 133 — тому й довше",
    decision: null,
    tag: null,
    tagTone: "muted",
    externalProductId: null,
    prompt: null,
    question: null,
  },
];

export interface MockOptions {
  /** Кроки, які `/api/progress/{key}` віддає ПОКИ збірка йде (02.09). */
  progress?: TraceStep[];
  /** Куди складати відповіді на питання агента (#285). */
  onAnswer?: (answer: { questionId: string; optionId: string }) => void;
  /** Скільки мілісекунд збірка «думає» до відповіді: без затримки екран
      збору не встигає показатись, і живі кроки нема на чому перевіряти. */
  buildDelayMs?: number;
  /** Чим відповідає `/api/auth/session`. `null` — бекенда немає взагалі. */
  session?: object | null;
  /** Чим відповідає `/api/place`. Тут перевіряються ОБИДВА стани: адреса є
   *  і адреси немає (гість, який доставку ще не замовляв). */
  place?: Place;
  /**
   * Адреса не прочиталась (502). Стан, у якому вікно вибору потрібне
   * НАЙБІЛЬШЕ -- і в якому воно до 02.09 не відкривалось узагалі (#253).
   */
  placeDown?: boolean;
  /** Накладка на зібраний кошик: стани, які інакше довелось би відтворювати
   *  цілим прогоном (нерозпізнаний намір, порожній на цей слот вид). */
  basket?: Partial<Basket>;
  /** Що саме пішло в `/api/basket`. Уточнення — це ДРУГИЙ запит, і перевірити
   *  «відповідь доїхала» можна тільки по його тілу. */
  onBuild?: (body: Record<string, unknown>) => void;
  /** Рядки, на яких акція зникла, поки кошик писали (#265). */
  promoGone?: string[];
  /** Попередження кошика після запису (#272). */
  warnings?: string[];
  /** Що поїхало ДОБОРОМ. Після #244 відповідь на уточнення їде саме сюди, а
   *  не повною перезбіркою -- і «відповідь доїхала» перевіряється тут. */
  onRefill?: (body: Record<string, unknown>) => void;
  /** Добір повертає те саме питання -- агент перепитав (#281). */
  reask?: boolean;
  /**
   * Добір відмовив з 409 і цим текстом (#302).
   *
   * Законна відповідь: дописаного виду на цій полиці немає. Стан окремо не
   * відтворити -- він народжується РІЗНИЦЕЮ між планом і полицею, а не
   * всередині плану.
   */
  refillError?: string;
  /** Скільки триває добір у фікстурі; за замовчуванням `REFILL_MS`. */
  refillDelayMs?: number;
  /** Коди відмови кошика і їхні речення (#251). Разом, як їх рахує сервер. */
  blockers?: string[];
  blockerNotes?: string[];
  retryHelps?: boolean;
  /** Що поїхало дешевим шляхом погодження замін (#77). Окремо від `onBuild`
   *  навмисно: головне в цій задачі — що ПОВНОГО прогону не було. */
  onSwaps?: (body: Record<string, unknown>) => void;
  /** Тижнева рамка в панелі бюджету: скільки вже витрачено за чеками. */
  week?: WeekSpend;
  /**
   * Способи отримання. Живий замір 22.08 дав на адресу гостя ТРИ типи з
   * п'яти відомих, а скарга звучала як «завжди доступний тільки кур'єр»
   * (#101): перелік, у якому жива одна плитка, окремо відтворити нічим.
   */
  delivery?: DeliveryOption[];
  /**
   * Умов доставки ще НЕМАЄ: `'slow'` — відповідь іде секунди, `'dead'` —
   * запит упав (наживо це 502 «MCP «Сільпо»: …», `api/app.py`).
   *
   * Обидва стани окремо не відтворити, а до #164 в них стояв скелет із
   * ПРИЧИНАМИ: гість читав «самовивіз — у хакатон-демо не передбачено» на
   * кожному відкритті старту, а на відмові — назавжди.
   */
  deliveryWait?: "slow" | "dead";
  /** Стан кошика акаунта до кліку. `'unknown'` — читання впало (502). */
  cart?: CartState | "unknown";
  /**
   * Що вже лежить у кошику «Сільпо» поза планом (#30).
   *
   * Живий прогін 15.08: другий `--commit` записав 11 рядків, а в кошику
   * лишилось 14. Стан відтворити інакше нічим — він народжується між ДВОМА
   * прогонами, а не всередині одного.
   */
  carryOver?: CarryOverLine[];
  /**
   * Комора: `'slow'` — відповідь із затримкою (наживо холодний прогін 15,6 с,
   * `docs/measured.md`), `'empty'` — чеків немає взагалі. Обидва стани
   * інакше не відтворити, а виглядали вони однаково (#56). `'long'` — комора
   * живого акаунта: 41 вид, тобто рівно та довжина, у якій вид шукається
   * прокруткою (#93). `'fresh'` — чеки Є, а рядків немає: стан кожного
   * гостя одразу після першої доставки, і він теж виглядав як «чеків
   * не знайшлось» (#38). `'small-pool'` — чеки є і комора повна, а
   * назбирується з них менше за коридор названої суми (#206): чип мусить
   * сказати СКІЛЬКИ, а не мовчати про це до кінця збірки.
   */
  pantry?:
    | "slow"
    | "empty"
    | "long"
    | "twins"
    | "fresh"
    | "delivery-only"
    | "small-pool"
    | "one-aisle"
    | "dead";
  /**
   * Слово гостя про рядок: `'slow'` — відповідь через півтори секунди (наживо
   * дотик коштує 3744 мс, замір 26.08), `'dead'` — сховище не відповіло.
   *
   * Обидва стани окремо не відтворити, а саме в них живе #145: поки відповідь
   * їде, гість тисне ще раз, і до 28.08 друге натискання мовчки не робило
   * нічого. Мовчазна відмова від зламаної кнопки не відрізняється.
   */
  pantryWrite?: "slow" | "dead";
  /**
   * Петля комори -- ДРУГА відповідь (#330). `'quiet'` (за замовчуванням) --
   * петля покрутилась і нічого не бракувало; `'found'` -- знайшла і рядок
   * заговорив інакше; `'dead'` -- не приїхала взагалі.
   *
   * Три стани, бо на екрані вони мусять розрізнятись: «перевірив, усе
   * гаразд» і «не перевіряв» -- різні відповіді, а сплутати їх означає
   * повторити #209 поверхом вище.
   */
  pantryLoop?:
    | "quiet"
    | "found"
    | "dead"
    | "slow"
    | "stuck"
    | "twinned"
    /** Петля спинилась на питаннях агента і продовжується з відповіддю (#386). */
    | "asking";
  /** Скільки тримати відповідь на ВІДПОВІДЬ гостя, мс (типово 1,5 с). */
  answerHoldMs?: number;
  /**
   * Петля віддала рядок, який ЗЛИВАЄ два колишні (#302).
   *
   * Так і буває на холодному акаунті: перша відмальовка ділить за `kind_key`,
   * петля називає види, і два рядки стають одним. Фікстура, яка завжди віддає
   * рівно ті самі id, цього стану не має за побудовою -- і саме тому жоден із
   * 356 тестів не бачив дубля ключа, від якого падав увесь екран.
   */
  /**
   * ХОЛОДНА комора: рядки вже приїхали, але БЕЗ мітки виду (#341).
   *
   * Стан, який гість бачить першим на свіжому акаунті: назви ще з КАСИ
   * («Макаронні вироби Barilla Спагеті»), а називає їх петля наступну
   * хвилину. Окремо від `pantry: "slow"`, бо це інша половина того самого
   * очікування -- там комори ще немає взагалі, тут вона є і неправдива.
   */
  pantryCold?: boolean;
  /**
   * `slow` -- петля, яка ЙДЕ (#341): відповідь тримається, а канал прогресу
   * тим часом віддає кроки. Без затримки перевіряти живі кроки нема на чому:
   * відповідь приїжджає першим же тиком, і проміжний стан не існує.
   */
  /**
   * Збірка з затримкою. Наживо вона триває близько тридцяти секунд, з яких
   * 73% — один виклик моделі (виміряно 20.08), і саме ці секунди екран
   * заповнює думками агента. З миттєвою відповіддю фікстури той екран не
   * встигає навіть з'явитись, тобто перевірити його нічим.
   */
  build?: "slow";
  /**
   * «Оформити» віддає не наш JSON, а чуже тіло з кодом.
   *
   * Так виглядає жива поломка 03.09: Cloudflare підміняє 502 від origin
   * своєю HTML-сторінкою, і фронт друкував її в банер (#298). Фікстура
   * повторює саме це -- інакше перевіряти нема чого: наш сервер такого
   * тіла не віддає ніколи, а гість його побачив.
   */
  checkoutForeign?: { status: number; body: string };
  /** Обмеження з профілю «Сільпо». Порожньо — як у живого акаунта. */
  profile?: Exclusion[];
  /** Правила гостя, які вже лежать у базі на момент відкриття сторінки. */
  rules?: Exclusion[];
  /** Сховище правил не відповідає: правки лишаються в браузері, і про це кажуть. */
  rulesDown?: boolean;
  /** Читання правил живе, а запис лежить — стан, у якому синхронізація рветься
      посеред циклу і мовчки губила недонесене (#119). */
  ruleWritesDown?: boolean;
  /** Стан стелі прогонів. Замовчування — робочий лічильник із запасом. */
  quota?: Quota;
  /**
   * Бар (#5). Порожній він буває з ТРЬОХ різних причин, і поради в них
   * різні — покупок не видно, напоїв серед звичного немає, види ще не
   * названі агентом. Три готові стани — `BAR_NO_RECEIPTS`, `BAR_NO_DRINKS`,
   * `BAR_UNNAMED`: інакше вони на екрані нерозрізненні.
   */
  bar?: Bar;
}

export const QUOTA: Quota = {
  blocked: false,
  scope: null,
  headline: "прогонів: 1 з 6 у цій сесії, 3 з 12 за добу",
  action: null,
  left: 5,
  resetsAt: null,
  contact: null,
  toll: {
    runs: 4,
    usd: 0.0213,
    unpriced: 0,
    tokensIn: 38412,
    tokensOut: 2907,
    guestUsd: null,
  },
};

export const QUOTA_SPENT: Quota = {
  blocked: true,
  scope: "day",
  headline: "на сьогодні стеля прогонів вичерпана: 12 з 12",
  action:
    "оновиться опівночі за Києвом, через 7 год. Комора і решта екранів працюють. " +
    "Потрібно більше — напиши автору",
  left: 0,
  resetsAt: "2026-08-24T21:00:00+00:00",
  contact: "https://github.com/mykhailoklimnyk/pantry/issues",
  toll: {
    runs: 12,
    usd: 0.1904,
    unpriced: 0,
    tokensIn: 402881,
    tokensOut: 21044,
    guestUsd: null,
  },
};

/** Скільки триває «повільна» збірка у фікстурі: досить, щоб агент устиг
 *  сказати перше про дім гостя (перша репліка — на сьомій секунді). */
export const BUILD_SLOW_MS = 10_000;

const CART_STATE: CartState = {
  rows: 7,
  total: 1253.4,
  slot: {
    start: "2026-08-14T11:00:00+03:00",
    end: "2026-08-14T13:00:00+03:00",
    note: null,
  },
};

const EMPTIED: CartState = { rows: 0, total: 0, slot: null };

/**
 * Чим сервер відмовляє входу Б, коли доводити нема чого.
 *
 * Копія `EMPTY_CART_NOTE` з `agent/cart.py`; точне формулювання пінить
 * `tests/test_agent_cart.py`, а тут воно потрібне, щоб перевірити головне —
 * що гість читає слова про СВІЙ кошик, а не нашу класифікацію входів (#89).
 */
const EMPTY_CART_NOTE =
  "кошик у «Сільпо» порожній — доводити до дверей нема чого. " +
  "Наповни його в «Сільпо» або натисни «Зібрати на тиждень»: " +
  "зберу кошик із твоїх покупок";

const WEEK: WeekSpend = {
  spent: 1000,
  receipts: 2,
  since: "2026-08-17T00:00:00",
};

const PLACE: Place = {
  address: "Вінниця, вулиця Соборна, 1, кв. 2",
  tag: null,
  branch: "Вінниця, вулиця Соборна, 46",
  branchId: "demo-branch-1",
  source: "address",
  note: "магазин збирання визначено за цією адресою",
  deliveryTypes: ["DeliveryHome", "SelfPickup"],
  saved: [
    {
      id: "demo-address-1",
      label: "Вінниця, вулиця Соборна, 1, кв. 2",
      tag: null,
      latitude: 49.22,
      longitude: 28.45,
    },
  ],
};

/** Що віддає пошук адреси: варіанти, серед яких є й інше місто. */
const FOUND: PlaceOption[] = [
  {
    id: null,
    label: "Вінниця, вулиця Пирогова, 20",
    tag: null,
    latitude: 49.23,
    longitude: 28.46,
  },
  {
    id: null,
    label: "Київська область, Боярка, вулиця Хрещатик, 1",
    tag: null,
    latitude: 50.31,
    longitude: 30.29,
  },
];

/**
 * Підняти весь `/api` як фікстуру.
 *
 * Один хендлер на все, а не роут на кожен шлях: тест, який забув замокати
 * один ендпоїнт, отримував би від прев'ю-сервера HTML замість JSON — і падав
 * би з помилкою розбору, а не з назвою того, чого бракує.
 */
export const PANTRY_SLOW_MS = 30_000;

export const DELIVERY_SLOW_MS = 10_000;

/** Що гість робить із кошиком ПОВЗ Комору — вже після старту застосунку. */
export interface Silpo {
  /**
   * Гість спорожнив кошик у самому «Сільпо».
   *
   * Живий тест 20.08 (#89): оформив, пішов на оплату, видалив там товар.
   * Після цього і `/cart`, і `/basket` відповідають про НОВИЙ стан кошика —
   * а на екрані ще стоїть підпис, зроблений зі старого.
   */
  emptyCart(): void;
  /**
   * Сховище правил лягло і піднялось назад.
   *
   * Стан, який інакше не відтворити: правило, записане поки база мовчала,
   * живе тільки в браузері, і найтихіше воно зникає не від збою, а від
   * УСПІШНОЇ сусідньої правки (#45).
   */
  breakRules(): void;
  healRules(): void;
  /**
   * ЗАПИС правила падає, а читання лишається живим.
   *
   * Стан, який інакше не відтворити, і він не той самий, що `breakRules`:
   * відмова сервера на записі ділиться надвоє -- НОВЕ правило лишається на
   * екрані, ЗМІНА вже збереженого відкочується (#45). Обидві гілки видно
   * тільки тут.
   */
  breakRuleWrites(): void;
  healRuleWrites(): void;
  /**
   * Збірка падає на сервері.
   *
   * Стан, який інакше не відтворити: саме тут губився запит, що зламав, —
   * у список прогонів потрапляла лише УСПІШНА відповідь (#91). `null`
   * замість коду — відповідь, яка не доїхала взагалі.
   */
  breakBuild(status: number | null, detail?: string): void;
  healBuild(): void;
  /**
   * Умови доставки лягли і піднялись назад.
   *
   * Стан, який інакше не відтворити: названа відмова мусить лишати ДІЮ, а
   * перевірити дію можна лише тим, що після повтору вона щось дає (#164).
   */
  breakDelivery(): void;
  healDelivery(): void;
}

/**
 * Id дописаного виду — так само, як його рахує сервер (`core/pantry.py`):
 * ВІДБИТОК слова, а не саме слово. Тут воно спрощене до стабільного рядка:
 * фікстурі потрібен лише той самий id на той самий вид, а не крипта.
 *
 * Слово гостя в id не потрапляє навмисно — так само, як наживо: id їде в
 * шлях DELETE, а шляхи лишаються в логах проксі (ADR-03).
 */
function manualId(label: string): string {
  const key = label.trim().toLowerCase();
  let hash = 0;
  for (const ch of key) hash = (hash * 31 + ch.codePointAt(0)!) >>> 0;
  return `manual:${hash.toString(16)}`;
}

export async function mockApi(
  page: Page,
  options: MockOptions = {},
): Promise<Silpo> {
  const session = options.session === undefined ? SESSION : options.session;
  let place: Place = options.place ?? PLACE;
  let out = false;
  let llmKeyHeld = false;
  let cart: CartState | "unknown" = options.cart ?? CART_STATE;
  let buildBroken: { status: number | null; detail: string } | null = null;
  const written = new Map<string, PantryItem>();
  const fromPurchases = new Set<string>();
  let pantryMode: "receipts" | "manual" = "receipts";

  let barMode: "receipts" | "manual" = "receipts";

  const wanted = new Map<
    string,
    { label: string; atHome: boolean; why?: string | null; origin?: string }
  >();
  const savedSwaps = new Map<string, SavedSwap>();
  const barWritten = new Map<string, BarItem>();

  const plans = new Map<string, Map<string, string>>();

  const planOf = (runId: string) => new Map(plans.get(runId) ?? []);

  const barShelf = new Map<string, DrinkKind>();
  const shelfKey = (label: string) =>
    label.toLowerCase().split(/\s+/).filter(Boolean).slice(0, 2).join(" ");
  const onShelf = (item: BarItem): BarItem => {
    const said = barShelf.get(shelfKey(item.label));
    return said === undefined ? item : { ...item, kind: said, kindSaid: true };
  };

  const barSnapshot = (): Bar => ({
    ...BAR,
    items: (barMode === "manual"
      ? [...barWritten.values()]
      : [...BAR_ITEMS, ...barWritten.values()]
    ).map(onShelf),
    source: barMode,
    unlisted:
      barMode === "manual"
        ? BAR_ITEMS.filter((item) => !barWritten.has(item.id)).length
        : 0,
  });

  const pantrySnapshot = () =>
    pantryMode === "manual"
      ? pantryState([...written.values()], {
          receipts: 118,
          kinds: 143,
          source: "manual",
          unlisted: PANTRY.filter((item) => !written.has(item.id)).length,
          outside: PANTRY.filter((item) => !written.has(item.id))
            .slice(0, 4)
            .map((item) => item.label),
        })
      : pantryState(
          [
            ...[...written.values()].filter(
              (row) => !fromPurchases.has(row.id),
            ),
            ...PANTRY,
          ],
          { receipts: 118, kinds: 143 },
        );
  const retimed_rows = new Map<string, PantryItem>();
  let served = 0;
  let refillBase: Basket | null = null;
  let own: Exclusion[] = (options.rules ?? RULES).map((rule) => ({ ...rule }));
  let rulesDown = options.rulesDown ?? false;
  let ruleWritesDown = options.ruleWritesDown ?? false;
  let deliveryDown = options.deliveryWait === "dead";
  split_intents.clear();
  hidden_kinds.clear();
  lastDrawn = null;
  runsMade = 0;

  await page.route("**/api/**", async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^.*\/api/, "");

    if (path.startsWith("/progress/")) {
      if (path.endsWith("/answer")) {
        const said = JSON.parse(route.request().postData() ?? "{}") as {
          questionId: string;
          optionId: string;
        };
        options.onAnswer?.(said);
        await route.fulfill({ json: { taken: true } });
        return;
      }
      await route.fulfill({
        json: {
          steps:
            options.pantryLoop === "slow"
              ? PANTRY_LOOP_STEPS
              : (options.progress ?? []),
          done: false,
        },
      });
      return;
    }

    if (path === "/auth/llm-key") {
      if (route.request().method() === "DELETE") {
        llmKeyHeld = false;
        await route.fulfill({
          json: { ...(session as object), llmKey: false },
        });
        return;
      }
      const body = route.request().postDataJSON() as { key?: string };
      if (!body.key || !body.key.startsWith("sk-")) {
        await route.fulfill({
          status: 400,
          json: {
            detail: "це не схоже на ключ OpenAI — він починається з «sk-»",
          },
        });
        return;
      }
      llmKeyHeld = true;
      await route.fulfill({ json: { ...(session as object), llmKey: true } });
      return;
    }

    if (path === "/auth/session") {
      if (session === null) {
        await route.fulfill({ status: 404, body: "нема такого" });
        return;
      }
      await route.fulfill({
        json: out
          ? { connected: false }
          : { ...(session as object), llmKey: llmKeyHeld },
      });
      return;
    }
    if (path === "/auth/logout") {
      out = true;
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (path === "/health") {
      await route.fulfill({
        json: {
          database: true,
          loginReady: true,
          version: null,
        } satisfies Health,
      });
      return;
    }
    if (path === "/models") {
      await route.fulfill({ json: MODELS });
      return;
    }
    if (path === "/quota") {
      const base = options.quota ?? QUOTA;
      const toll =
        base.toll === null
          ? null
          : {
              ...base.toll,
              runs: base.toll.runs + runsMade,
              usd:
                base.toll.usd === null
                  ? null
                  : base.toll.usd + runsMade * 0.0071,
              tokensIn: base.toll.tokensIn + runsMade * 9314,
              tokensOut: base.toll.tokensOut + runsMade * 708,
            };
      await route.fulfill({ json: { ...base, toll } });
      return;
    }
    if (path === "/exclusions") {
      await route.fulfill({ json: options.profile ?? [] });
      return;
    }
    if (path.startsWith("/rules")) {
      if (rulesDown) {
        await route.fulfill({
          status: 503,
          json: { detail: "сховище правил не відповідає" },
        });
        return;
      }
      const method = route.request().method();
      if (ruleWritesDown && method !== "GET") {
        await route.fulfill({
          status: 503,
          json: { detail: "сховище правил не відповідає" },
        });
        return;
      }
      const ident = decodeURIComponent(path.slice("/rules/".length));
      if (method === "POST") {
        const body = route.request().postDataJSON() as {
          label: string;
          active?: boolean;
        };
        const label = body.label.trim().replace(/\s+/g, " ");
        const same = own.find(
          (rule) => rule.label.toLowerCase() === label.toLowerCase(),
        );
        if (same) same.active = body.active !== false;
        else {
          own.push({
            id: `rule:written-${own.length + 1}`,
            label,
            permanent: false,
            active: body.active !== false,
          });
        }
      } else if (method === "PATCH") {
        const body = route.request().postDataJSON() as { active: boolean };
        const target = own.find((rule) => rule.id === ident);
        if (!target) {
          await route.fulfill({
            status: 404,
            json: { detail: "такого правила немає" },
          });
          return;
        }
        target.active = body.active;
      } else if (method === "DELETE") {
        own = own.filter((rule) => rule.id !== ident);
      }
      await route.fulfill({ json: own });
      return;
    }
    if (path === "/delivery-options") {
      if (options.deliveryWait === "slow") {
        await new Promise((done) => setTimeout(done, DELIVERY_SLOW_MS));
      }
      if (deliveryDown) {
        await route.fulfill({
          status: 502,
          json: { detail: "MCP «Сільпо»: silpo_get_time_slots не відповів" },
        });
        return;
      }
      await route.fulfill({ json: options.delivery ?? DELIVERY });
      return;
    }
    if (path === "/place/search") {
      const body = route.request().postDataJSON() as { text: string };
      await route.fulfill({ json: body.text.trim() ? FOUND : [] });
      return;
    }
    if (path === "/place") {
      if (options.placeDown) {
        await route.fulfill({
          status: 502,
          body: "MCP «Сільпо»: silpo_get_my_delivery_addresses не відповів",
        });
        return;
      }
      if (route.request().method() === "POST") {
        const chosen = route.request().postDataJSON() as PlaceOption;
        place = {
          ...place,
          address: chosen.label,
          tag: chosen.tag ?? null,
          branch: "Вінниця, вулиця Келецька, 117",
          branchId: "demo-branch-2",
          source: "address",
          note: "магазин збирання визначено за цією адресою",
        };
      }
      await route.fulfill({ json: place });
      return;
    }
    if (path === "/pantry/source" && route.request().method() === "PUT") {
      pantryMode =
        (route.request().postDataJSON() as { mode?: "receipts" | "manual" })
          .mode ?? "receipts";
      await route.fulfill({
        json: { ...pantrySnapshot(), changed: written.size },
      });
      return;
    }
    if (path === "/pantry/refine") {
      const seen = Number(
        (route.request().postDataJSON() as { seen?: number })?.seen ?? 0,
      );
      const onward = <T extends { trace?: unknown[] }>(body: T): T =>
        seen > 0 ? { ...body, trace: [] } : body;
      if (options.pantryLoop === "stuck") {
        await new Promise((done) => setTimeout(done, 30_000));
        await route.fulfill({ json: onward(lastDrawn ?? pantrySnapshot()) });
        return;
      }
      if (options.pantryLoop === "slow") {
        await new Promise((done) => setTimeout(done, 1_200));
        const drawn: Pantry = lastDrawn ?? pantrySnapshot();
        await route.fulfill({
          json: onward({ ...drawn, refined: "уточнено: 1" }),
        });
        return;
      }
      if (options.pantryLoop === "asking") {
        const snapshot: Pantry = lastDrawn ?? pantrySnapshot();
        const body = await route.request().postDataJSON();
        const keyed = Object.keys(body?.answers ?? {}).filter(
          (label) => (body?.kinds ?? {})[label],
        );
        const answered = keyed.length > 0;
        if (answered) {
          await new Promise((done) => setTimeout(done, options.answerHoldMs ?? 1500));
        }
        await route.fulfill({
          json: onward({
            ...snapshot,
            refined: answered ? "уточнено: 3" : "уточнено: 0",
            asked: answered
              ? [
                  {
                    label: "молоко",
                    ask: "як швидко у вас закінчується молоко?",
                    covers: ["кефір"],
                    kind: "молоко ферма",
                    coverKinds: ["кефір галичина"],
                  },
                ]
              : [
                  {
                    label: "хліб",
                    ask: "як швидко у вас закінчується хліб?",
                    covers: ["булка", "батон"],
                    kind: "хліб житній",
                    coverKinds: ["булка з", "батон нарізний"],
                  },
                ],
          }),
        });
        return;
      }
      if (options.pantryLoop === "twinned") {
        const snapshot: Pantry = lastDrawn ?? pantrySnapshot();
        const first = snapshot.items[0]!;
        await route.fulfill({
          json: onward({
            ...snapshot,
            items: [
              first,
              { ...snapshot.items[1]!, id: first.id },
              ...snapshot.items.slice(2),
            ],
            refined: "уточнено: 1",
          }),
        });
        return;
      }
      if (options.pantryLoop === "dead") {
        await route.fulfill({ status: 503, json: { detail: "петля мовчить" } });
        return;
      }
      const snapshot: Pantry = lastDrawn ?? pantrySnapshot();
      if (options.pantryLoop !== "found") {
        await route.fulfill({
          json: onward({ ...snapshot, refined: "нічого не бракувало" }),
        });
        return;
      }
      await route.fulfill({
        json: {
          ...snapshot,
          refined: "уточнено: 1",
          items: snapshot.items
            .map((row, at) =>
              at === 0
                ? { ...row, named: true, sanity: "паляничку з'їдають за раз" }
                : row,
            )
            .reverse(),
        },
      });
      return;
    }
    if (path === "/pantry/generate") {
      PANTRY.forEach((item, at) => {
        written.set(item.id, {
          ...item,
          source: at === PANTRY.length - 1 ? "manual" : item.source,
        });
        fromPurchases.add(item.id);
      });
      await route.fulfill({
        json: { ...pantrySnapshot(), changed: PANTRY.length },
      });
      return;
    }
    if (path === "/pantry/items" && route.request().method() === "DELETE") {
      const wiped = written.size;
      written.clear();
      fromPurchases.clear();
      await route.fulfill({ json: { ...pantrySnapshot(), changed: wiped } });
      return;
    }
    if (path === "/pantry/manual") {
      const { label } = route.request().postDataJSON() as { label: string };
      const known = label.trim().toLowerCase().startsWith("свинин");
      const said = label.trim().toLowerCase();
      const tracked = PANTRY.find((row) => {
        const kind = row.label.toLowerCase();
        return said === kind || said.startsWith(`${kind} `);
      });
      if (tracked) {
        await route.fulfill({ json: tracked satisfies PantryItem });
        return;
      }
      const written_row: PantryItem = {
        wanted: false,
        mandate: null,
        writtenAs: [],
        parts: [],
        group: null,
        aisle: null,
        id: manualId(label),
        label,
        qty: null,
        usualQty: null,
        unit: known ? "кг" : "",
        leftRatio: null,
        daysLeft: null,
        cycleDays: null,
        cycleSaid: false,
        named: true,
        state: known
          ? "додано вручну · у чеках це Свинина охолоджена, брав 2 — цикл рахується з 3, беру в наступний кошик"
          : "додано вручну · у чеках «Сільпо» такого немає — беру в наступний кошик",
        keeps: null,
        sanity: null,
        trust: "",
        ask: false,
        runningOut: false,
        promo: null,
        arrived: null,
        usual: null,
        source: "manual",
        imageUrl: null,
      };
      written.set(written_row.id, written_row);
      fromPurchases.delete(written_row.id);
      await route.fulfill({ json: written_row });
      return;
    }
    if (
      path.startsWith("/pantry/manual/") &&
      route.request().method() === "DELETE"
    ) {
      const id = decodeURIComponent(path.slice("/pantry/manual/".length));
      if (!id.startsWith("manual:")) {
        await route.fulfill({
          status: 422,
          json: { detail: "прибрати можна лише те, що ти додав руками" },
        });
        return;
      }
      written.delete(id);
      fromPurchases.delete(id);
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (path === "/pantry" && route.request().method() === "PATCH") {
      const said = route.request().postDataJSON() as {
        id: string;
        action:
          | "bought"
          | "qty"
          | "cycle"
          | "forget_cycle"
          | "hide"
          | "unhide"
          | "split"
          | "unsplit";
        qty: number;
        days: number;
        group?: string;
      };
      if (options.pantryWrite === "dead") {
        await route.fulfill({
          status: 503,
          json: { detail: "не вдалось запам'ятати — скажи ще раз за мить" },
        });
        return;
      }
      if (options.pantryWrite === "slow") {
        await new Promise((done) => setTimeout(done, PANTRY_WRITE_MS));
      }
      const base = pantryRows(options.pantry);
      if (said.action === "hide") hidden_kinds.add(said.id);
      if (said.action === "unhide") {
        for (const id of hidden_kinds) {
          const row = base.find((item) => item.id === id);
          if (row?.label === said.id || id === said.id) hidden_kinds.delete(id);
        }
      }
      if (said.action === "split" && said.group) split_intents.add(said.group);
      if (said.action === "unsplit" && said.group)
        split_intents.delete(said.group);
      if (said.action === "cycle") {
        const row = base.find((item) => item.id === said.id);
        if (row)
          retimed_rows.set(said.id, retimed(row, said.days, sinceOf(row)));
      } else if (said.action === "forget_cycle") {
        retimed_rows.delete(said.id);
      }
      const rows = base.map((item) => {
        const current = retimed_rows.get(item.id) ?? item;
        if (item.id !== said.id) return current;
        if (
          said.action === "cycle" ||
          said.action === "forget_cycle" ||
          said.action === "hide" ||
          said.action === "unhide" ||
          said.action === "split" ||
          said.action === "unsplit"
        )
          return current;
        return marked(current, said.action, said.qty);
      });
      await route.fulfill({
        json: pantryState(apartOf(shownOnly(rows)), {
          ...hiddenNow(base),
          apart: [...split_intents],
        }),
      });
      return;
    }
    if (path === "/pantry") {
      if (options.pantry === "dead") {
        await route.fulfill({
          status: 502,
          json: { detail: "MCP «Сільпо» не відповів" },
        });
        return;
      }
      if (options.pantry === "empty") {
        await route.fulfill({
          json: pantryState([...written.values()], { receipts: 0, kinds: 0 }),
        });
        return;
      }
      if (options.pantry === "delivery-only") {
        await route.fulfill({
          json: pantryState([], { receipts: 0, kinds: 40, orders: 76 }),
        });
        return;
      }
      if (options.pantry === "small-pool") {
        await route.fulfill({
          json: pantryState(PANTRY, {
            receipts: 118,
            kinds: 143,
            targetEstimate: 600,
          }),
        });
        return;
      }
      if (options.pantry === "fresh") {
        await route.fulfill({
          json: pantryState([], { receipts: 2, kinds: 7 }),
        });
        return;
      }
      if (options.pantry === "slow") {
        await new Promise((done) => setTimeout(done, PANTRY_SLOW_MS));
      }
      if (options.pantryCold) {
        const cold = pantryState(pantryRows(options.pantry), hiddenNow([]));
        await route.fulfill({
          json: {
            ...cold,
            items: cold.items.map((row) => ({ ...row, named: false })),
          },
        });
        return;
      }
      await route.fulfill({
        json: pantryState(
          listedIn(
            apartOf(
              shownOnly([
                ...written.values(),
                ...pantryRows(options.pantry).map(
                  (item) => retimed_rows.get(item.id) ?? item,
                ),
              ]),
            ),
            new Set([...wanted.values()].map((row) => row.label)),
          ),
          {
            ...hiddenNow(pantryRows(options.pantry)),
            apart: [...split_intents],
          },
        ),
      });
      return;
    }
    if (path === "/cart") {
      if (cart === "unknown") {
        await route.fulfill({ status: 502, body: "MCP «Сільпо»: не відповів" });
        return;
      }
      await route.fulfill({ json: cart });
      return;
    }
    if (path === "/week-spend") {
      await route.fulfill({ json: options.week ?? WEEK });
      return;
    }
    if (path === "/list") {
      if (route.request().method() === "POST") {
        const { label, atHome } = route.request().postDataJSON() as {
          label: string;
          atHome?: boolean;
        };
        const said = label.trim();
        wanted.set(`manual:${said}`, {
          label: said,
          atHome: atHome ?? true,
          origin: "guest",
          why: null,
        });
      }
      await route.fulfill({
        json: [...wanted].map(([id, row]) => ({
          id,
          label: row.label,
          why: row.why ?? null,
          atHome: row.atHome,
        })),
      });
      return;
    }
    if (path === "/pantry/next-list") {
      const rows = pantrySnapshot().items.filter(
        (item) => item.source !== "manual" && item.runningOut,
      );
      const changes: string[] = [];
      const alive = new Set<string>();
      for (const item of rows) {
        const key = `manual:${item.label}`;
        alive.add(key);
        if (wanted.has(key)) continue;
        wanted.set(key, {
          label: item.label,
          atHome: true,
          origin: "agent",
          why: "закінчилось сьогодні",
        });
        changes.push(`додав ${item.label}`);
      }
      for (const [key, row] of [...wanted]) {
        if (row.origin === "agent" && !alive.has(key)) {
          wanted.delete(key);
          changes.push(`зняв ${row.label} — більше не закінчується`);
        }
      }
      await route.fulfill({
        json: {
          rows: [...wanted].map(([id, row]) => ({
            id,
            label: row.label,
            why: row.why ?? null,
            atHome: row.atHome,
          })),
          changes,
          note: `агент склав список: ${rows.length} з ${rows.length}`,
        },
      });
      return;
    }
    if (path.startsWith("/list/") && route.request().method() === "DELETE") {
      wanted.delete(decodeURIComponent(path.slice("/list/".length)));
      await route.fulfill({
        json: [...wanted].map(([id, row]) => ({ id, ...row })),
      });
      return;
    }
    if (path === "/bar") {
      await route.fulfill({ json: options.bar ?? barSnapshot() });
      return;
    }
    if (path === "/bar/source" && route.request().method() === "PUT") {
      barMode =
        (route.request().postDataJSON() as { mode?: "receipts" | "manual" })
          .mode ?? "receipts";
      await route.fulfill({ json: barSnapshot() });
      return;
    }
    if (path === "/bar/group" && route.request().method() === "PUT") {
      const said = route.request().postDataJSON() as {
        label: string;
        kind: DrinkKind | null;
      };
      const key = shelfKey(said.label);
      if (said.kind === null) barShelf.delete(key);
      else barShelf.set(key, said.kind);
      await route.fulfill({ json: barSnapshot() });
      return;
    }
    if (path === "/bar/generate") {
      for (const item of BAR_ITEMS) barWritten.set(item.id, { ...item });
      await route.fulfill({ json: barSnapshot() });
      return;
    }
    if (path === "/bar/items" && route.request().method() === "DELETE") {
      barWritten.clear();
      await route.fulfill({ json: barSnapshot() });
      return;
    }
    if (path === "/bar/manual" && route.request().method() === "POST") {
      const { label } = route.request().postDataJSON() as { label: string };
      const said = label.trim();
      barWritten.set(`manual:${said}`, {
        id: `manual:${said}`,
        label: said,
        kind: said.toLowerCase().startsWith("віск") ? "strong" : null,
        times: 0,
        daysSince: null,
        source: "manual",
        kindSaid: false,
        usual: null,
        priceFrom: null,
        priceTo: null,
        forkNote: "",
      });
      await route.fulfill({ json: barSnapshot() });
      return;
    }
    if (
      path.startsWith("/bar/manual/") &&
      route.request().method() === "DELETE"
    ) {
      barWritten.delete(decodeURIComponent(path.slice("/bar/manual/".length)));
      await route.fulfill({ json: barSnapshot() });
      return;
    }
    if (path === "/basket") {
      runsMade += 1;
      const body = route.request().postDataJSON() as {
        source?: string;
        delivery?: string;
        answers?: unknown[];
        autoSwap?: boolean;
        swaps?: {
          externalProductId: string;
          policy: string;
          chain: string[];
        }[];
      };
      options.onBuild?.(body as Record<string, unknown>);
      if (options.buildDelayMs) {
        await new Promise((resolve) =>
          setTimeout(resolve, options.buildDelayMs),
        );
      }
      if (buildBroken !== null) {
        if (buildBroken.status === null) {
          await route.abort("failed");
          return;
        }
        await route.fulfill({
          status: buildBroken.status,
          json: { detail: buildBroken.detail },
        });
        return;
      }
      if (options.build === "slow") {
        await new Promise((done) => setTimeout(done, BUILD_SLOW_MS));
      }
      if (body?.source === "cart" && cart !== "unknown" && cart.rows === 0) {
        await route.fulfill({ status: 409, json: { detail: EMPTY_CART_NOTE } });
        return;
      }
      const built =
        body?.source === "cart"
          ? cartBasket(body.delivery)
          : basket(body?.delivery);
      const made = body?.autoSwap ? withAutoSwap(built) : built;
      refillBase = null;
      const override = { ...(options.basket ?? {}) };
      if ((body?.answers ?? []).length > 0) override.questions = [];
      served += 1;
      await route.fulfill({
        json: {
          ...withSwaps(made, body?.swaps ?? []),
          runId: `e2e-${served}`,
          ...override,
        },
      });
      return;
    }
    if (path.endsWith("/options")) {
      const wanted = (url.searchParams.get("q") ?? "").trim().toLowerCase();
      await route.fulfill({
        json: wanted
          ? SWAP_OPTIONS.filter((option) =>
              option.name.toLowerCase().includes(wanted),
            )
          : // Без запиту віддається ВИД, а в ньому чужого не буває за побудовою:
            SWAP_OPTIONS.filter((option) => option.sameKind !== false),
      });
      return;
    }
    if (path.endsWith("/correction")) {
      const body = route.request().postDataJSON() as {
        externalProductId: string;
        action: string;
      };
      const from = url.pathname.split("/").at(-2) ?? "";
      const plan = planOf(from);
      plan.set(body.externalProductId, body.action);
      served += 1;
      plans.set(`e2e-${served}`, plan);
      await new Promise((done) => setTimeout(done, 250));
      await route.fulfill({ json: corrected(plan, served) });
      return;
    }
    if (path === "/swaps/saved") {
      await route.fulfill({ json: [...savedSwaps.values()] });
      return;
    }
    if (
      path.startsWith("/swaps/saved/") &&
      route.request().method() === "DELETE"
    ) {
      savedSwaps.delete(decodeURIComponent(path.slice("/swaps/saved/".length)));
      await route.fulfill({ json: [...savedSwaps.values()] });
      return;
    }
    if (path.endsWith("/swaps")) {
      const body = route.request().postDataJSON() as {
        swaps?: {
          externalProductId: string;
          policy: string;
          chain: string[];
        }[];
        remember?: boolean;
      };
      options.onSwaps?.(body as Record<string, unknown>);
      if (body.remember) {
        for (const swap of body.swaps ?? []) {
          const line = basket().lines.find(
            (row) => row.externalProductId === swap.externalProductId,
          );
          if (!line || swap.chain.length === 0) continue;
          savedSwaps.set(`manual:${line.name}`, {
            id: `manual:${line.name}`,
            label: line.name,
            links: swap.chain.map(
              (article) =>
                line.chain?.find((alt) => alt.externalProductId === article)
                  ?.name ?? article,
            ),
          });
        }
      }
      served += 1;
      await route.fulfill({
        json: swapped(
          { ...basket(), ...(options.basket ?? {}) },
          body.swaps ?? [],
          served,
        ),
      });
      return;
    }
    if (path.endsWith("/cheaper")) {
      const body = route.request().postDataJSON() as {
        externalProductId: string;
        to: string;
      };
      served += 1;
      const before = { ...basket(), ...(options.basket ?? {}) };
      await route.fulfill({
        json: {
          ...before,
          runId: `run-${served}`,
          lines: before.lines.map((line) =>
            line.externalProductId === body.externalProductId && line.cheaper
              ? {
                  ...line,
                  externalProductId: line.cheaper.externalProductId,
                  name: line.cheaper.name,
                  price: line.cheaper.price,
                  cheaper: null,
                }
              : line,
          ),
        },
      });
      return;
    }
    if (path.endsWith("/refill")) {
      await new Promise((done) =>
        setTimeout(done, options.refillDelayMs ?? REFILL_MS),
      );
      const body = route.request().postDataJSON() as {
        intents?: string[];
        answers?: { intent: string }[];
      };
      options.onRefill?.(body as Record<string, unknown>);
      if (options.refillError !== undefined) {
        await route.fulfill({
          status: 409,
          json: { detail: options.refillError },
        });
        return;
      }
      served += 1;
      const next = refilled(
        refillBase ?? { ...basket(), ...(options.basket ?? {}) },
        body.intents ?? [],
        served,
        body.answers ?? [],
        options.reask ?? false,
      );
      refillBase = next;
      await route.fulfill({ json: next });
      return;
    }
    if (path.endsWith("/checkout")) {
      if (options.checkoutForeign) {
        await route.fulfill({
          status: options.checkoutForeign.status,
          contentType: "text/html",
          body: options.checkoutForeign.body,
        });
        return;
      }
      const asked = (route.request().postDataJSON() ?? {}) as {
        existing?: string;
      };
      const existing = asked.existing ?? "asking";
      const leftovers = options.carryOver ?? [];
      const left = leftovers.reduce((sum, row) => sum + row.total, 0);
      if (leftovers.length > 0 && existing === "asking") {
        await route.fulfill({
          json: {
            written: 0,
            skipped: [],
            blockers: [],
            blockerNotes: [],
            retryHelps: false,
            checkoutWebLink: null,
            totals: null,
            carryOver: { state: "asking", total: left, lines: leftovers },
            wantedBurned: [],
            mandateLost: [],
            stockCut: [],
            basket: null,
            unmandated: [],
            wantedStocked: [],
            promoGone: [],
            bonusAvailable: null,
            warnings: [],
            trace: [],
            cartWebLink: null,
            summary:
              `у кошику «Сільпо» вже лежить ${leftovers.length} рядків на ${left} грн, ` +
              "яких немає в цьому плані -- скажи, доповнити чи почати заново",
          } satisfies CheckoutResult,
        });
        return;
      }
      if (options.blockers && options.blockers.length > 0) {
        await route.fulfill({
          json: {
            written: buying.length,
            skipped: [],
            blockers: options.blockers,
            blockerNotes: options.blockerNotes ?? [],
            retryHelps: options.retryHelps ?? false,
            wantedBurned: [],
            mandateLost: [],
            stockCut: [],
            basket: null,
            unmandated: [],
            wantedStocked: [],
            promoGone: [],
            bonusAvailable: null,
            warnings: [],
            carryOver: null,
            checkoutWebLink: null,
            cartWebLink: "https://silpo.ua/checkout-new",
            totals: {
              products: 1156.83,
              discount: 0,
              delivery: 0,
              toPay: 1156.83,
              estimate: null,
            },
            trace: [],
            summary: `у кошик поїхало ${buying.length} рядків, але оформити його поки не можна`,
          } satisfies CheckoutResult,
        });
        return;
      }
      const burned = [...wanted.values()].map((row) => row.label);
      const stocked = [...wanted.values()]
        .filter((row) => row.atHome)
        .map((row) => row.label);
      wanted.clear();
      await route.fulfill({
        json: {
          written: buying.length,
          skipped: [],
          blockers: [],
          blockerNotes: [],
          retryHelps: false,
          wantedBurned: burned,
          mandateLost: [],
          unmandated: buying
            .filter((row) => row.needsApproval && row.mandate === null)
            .map((row) => row.name),
          wantedStocked: stocked,
          promoGone: options.promoGone ?? [],
          warnings: options.warnings ?? [],
          checkoutWebLink: "https://silpo.ua/checkout/e2e",
          stockCut: [],
          basket: null,
          cartWebLink: "https://silpo.ua/checkout-new",
          totals: {
            products: 1153.04,
            discount: 288.02,
            delivery: 89,
            toPay: 1104.04,
            estimate: 1253,
          },
          bonusAvailable: 340,
          carryOver:
            leftovers.length > 0
              ? { state: existing, total: left, lines: leftovers }
              : null,
          summary: `${buying.length} рядків у кошику, до оплати 1104.04 грн`,
        },
      });
      return;
    }
    await route.fulfill({
      status: 501,
      json: { detail: `фікстури для ${path} немає` },
    });
  });

  return {
    emptyCart() {
      cart = EMPTIED;
    },
    breakRules() {
      rulesDown = true;
    },
    healRules() {
      rulesDown = false;
    },
    breakRuleWrites() {
      ruleWritesDown = true;
    },
    healRuleWrites() {
      ruleWritesDown = false;
    },
    breakDelivery() {
      deliveryDown = true;
    },
    healDelivery() {
      deliveryDown = false;
    },
    breakBuild(status: number | null, detail = "модель не відповіла") {
      buildBroken = { status, detail };
    },
    healBuild() {
      buildBroken = null;
    },
  };
}

/** Кошик після правки рядка: сума й вага перераховані, рядок не зник. */
function corrected(applied: Map<string, string>, seq: number): Basket {
  const base = basket();
  const lines = base.lines.map((line) => {
    const action = applied.get(line.externalProductId);
    if (action === undefined) return line;
    const home = action === "still_have";
    return {
      ...line,
      reason: (home ? "at_home" : "cycle") as CartLine["reason"],
      explanation: home
        ? "ти сказав, що ще є вдома — не купую"
        : "ти сказав, що закінчилось раніше — беру",
    };
  });
  const left = lines.filter((line) => line.reason !== "at_home");
  const total = round(left.reduce((sum, l) => sum + l.qty * l.price, 0));
  const last = [...applied.keys()].at(-1) ?? "";
  const home = applied.get(last) === "still_have";
  const name =
    lines.find((line) => line.externalProductId === last)?.name ?? "";
  return {
    ...base,
    runId: `e2e-${seq}`,
    lines,
    total,
    totalWeightKg: round(
      left.reduce((sum, l) => sum + l.qty * (l.weightKg ?? 0), 0),
    ),
    trace: [
      ...base.trace,
      {
        id: `step-correction-${seq}`,
        seq: base.trace.length,
        tool: "agent.correction",
        args: {},
        durationMs: 3,
        calls: null,
        tokensIn: null,
        tokensOut: null,
        resultSummary: `${name}: ${home ? "ще є вдома" : "закінчилось раніше"}`,
        decision: `перерахував кошик: разом ${total} грн`,
        tag: "правка гостя",
        tagTone: "good",
        externalProductId: null,
        prompt: null,
        question: null,
      },
    ],
  };
}
