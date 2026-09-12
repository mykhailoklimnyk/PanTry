
declare const __BUILD_COMMIT__: string
declare const __BUILD_REPO__: string
declare const __BUILD_VERSION__: string

/** Повний sha коміта збірки. Порожній — збирали поза git. */
const COMMIT: string = __BUILD_COMMIT__

/** Календарна версія UI: `2026.08.16-1423`. */
export const UI_VERSION: string = __BUILD_VERSION__

/** Базова адреса репозиторію без `.git`. Порожня — посилання не буде. */
const REPO: string = __BUILD_REPO__

/** Короткий sha — те, що показують і чим шукають у git. */
export const SHORT: string = COMMIT.slice(0, 9)

/**
 * Посилання на коміт або `null`.
 *
 * `null`, а не «#»: посилання, яке нікуди не веде, гірше за його відсутність
 * — по ньому клікають і вирішують, що зламалось саме тут.
 */
export function commitUrl(sha: string = COMMIT): string | null {
  if (!REPO || !sha) return null
  return `${REPO}/commit/${sha}`
}

/**
 * Однакові коміти фронта і бекенда?
 *
 * Бекенд віддає свій у `/api/health`. Порожній чи невідомий — не «розбіжність»:
 * сказати «версії розійшлись» там, де просто нема з чим порівняти, означає
 * послати шукати неіснуючу проблему.
 */
export function matches(backend: string | null | undefined): boolean | null {
  if (!backend || !COMMIT) return null
  return backend === COMMIT
}
