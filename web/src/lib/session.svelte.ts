
import { forgetAutoSwap } from './consent'
import { forget as forgetRuleCache } from './rules'
import type { GuestLink } from './types'

export interface Link {
  /** Відповідь від сервера вже приходила: до неї показувати нічого не варто. */
  ready: boolean
  /** Чи є взагалі бекенд за цією адресою. */
  backend: boolean
  connected: boolean
  /** Коли закінчується доступ. Показуємо, бо «стежу до слота» на це спирається. */
  expiresAt: string | null
  /** Чому розірвано — словами. Причина живе поруч із кнопкою, не в стані. */
  note: string | null
  /**
   * Номер гостя серед перших десяти — і тільки якщо пасхалку ще не показували.
   *
   * Рішення ухвалює сервер і віддає його РІВНО ОДИН раз (`db/newcomers.py`),
   * тож фронту лишається показати і погасити. Тримати тут прапорець «уже
   * бачив» не треба: друга вкладка отримає `null` з тієї ж причини, з якої
   * його отримає завтрашній візит.
   */
  greet: number | null
  /**
   * Чи лежить у браузері ключ гостя до OpenAI (#197).
   *
   * Сам ключ сюди не приходить ніколи — він httpOnly. Тут відповідь на єдине
   * питання, потрібне екрану: показувати поле для ключа чи назву моделі, яку
   * цей ключ уже відмикає.
   */
  llmKey: boolean
}

export const link: Link = $state({
  ready: false,
  backend: false,
  connected: false,
  expiresAt: null,
  note: null,
  greet: null,
  llmKey: false,
})

/**
 * Спитати сервер про стан і, якщо треба, дати йому оновити токен.
 *
 * ЄДИНЕ місце, звідки починається оновлення: сервер робить його саме на цей
 * запит. Тому кличеться воно першим, до решти даних.
 */
export async function refresh(): Promise<void> {
  try {
    const response = await fetch('/api/auth/session', {
      headers: { accept: 'application/json' },
    })
    if (!response.ok) throw new Error(String(response.status))
    const reply = (await response.json()) as GuestLink
    link.backend = true
    link.connected = reply.connected === true
    link.expiresAt = reply.expiresAt ?? null
    link.note = reply.reason ?? null
    link.greet = reply.greet ?? null
    link.llmKey = reply.llmKey === true
  } catch {
    link.backend = false
    link.connected = false
    link.expiresAt = null
    link.greet = null
    link.llmKey = false
  } finally {
    link.ready = true
  }
}

/**
 * Доступ перестав діяти посеред роботи. Кличеться з розвилки даних на 401.
 *
 * Стан один на всі причини — «протух», «відкликано ззовні», «вийшов у іншій
 * вкладці». Лікування в них однакове, тож розрізняти їх станом нема сенсу;
 * причина живе текстом поруч із кнопкою.
 */
export function dropped(note: string): void {
  link.connected = false
  link.expiresAt = null
  link.note = note
}

/**
 * Пасхалку показали — гасимо номер.
 *
 * Сервер уже позначив показ у себе, тож повторно він його не віддасть; це
 * потрібно рівно для того, щоб заставка не відкрилась удруге на наступному
 * опиті стану в цій самій вкладці.
 */
export function greeted(): void {
  link.greet = null
}

/** Куди веде «Підключити»: повний перехід, а не fetch — це редірект на логін. */
export function connectUrl(): string {
  return `/api/auth/start?return_to=${encodeURIComponent(location.pathname)}`
}

/**
 * Вийти. Відкликання перевірене живим дослідом: воно справді вбиває токен і
 * б'є ТОЧКОВО, тож інший пристрій гостя працює далі (docs/mcp-facts.md).
 */
export async function disconnect(): Promise<void> {
  forgetRuleCache()
  forgetAutoSwap()
  try {
    await fetch('/api/auth/logout', { method: 'POST' })
  } catch {
  }
  await refresh()
}


/**
 * Покласти ключ гостя до OpenAI в його ж браузер. → причина відмови або null.
 *
 * Сесії «Сільпо» це не вимагає навмисно: ключ моделі до чужого акаунта
 * стосунку не має, і зв'язати два незалежні рішення гостя в одне означало б
 * не пустити його до швидкої моделі, поки він не підключив магазин.
 */
export async function saveLlmKey(key: string): Promise<string | null> {
  try {
    const response = await fetch('/api/auth/llm-key', {
      method: 'PUT',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: JSON.stringify({ key }),
    })
    if (!response.ok) {
      const reply = (await response.json().catch(() => null)) as { detail?: string } | null
      return reply?.detail ?? 'ключ не зберігся — спробуй ще раз'
    }
    link.llmKey = true
    return null
  } catch {
    return 'ключ не зберігся — мережа не відповіла'
  }
}

/** Прибрати ключ, не виходячи з акаунта «Сільпо». */
export async function forgetLlmKey(): Promise<void> {
  try {
    await fetch('/api/auth/llm-key', { method: 'DELETE' })
  } finally {
    link.llmKey = false
  }
}
