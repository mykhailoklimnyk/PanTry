
export const AUTOSWAP_KEY = 'komora:autoswap'

/** Чи гість дав стоячу згоду. Немає запису -- немає згоди. */
export function autoSwapGiven(): boolean {
  try {
    return localStorage.getItem(AUTOSWAP_KEY) === '1'
  } catch {
    return false
  }
}

/** Запам'ятати рішення гостя. */
export function rememberAutoSwap(given: boolean): void {
  try {
    localStorage.setItem(AUTOSWAP_KEY, given ? '1' : '0')
  } catch {
  }
}

/** Забути згоду: гість вийшов, і далі браузером користується вже не він. */
export function forgetAutoSwap(): void {
  try {
    localStorage.removeItem(AUTOSWAP_KEY)
  } catch {
  }
}
