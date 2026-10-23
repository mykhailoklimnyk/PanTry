
export const AUTOSWAP_KEY = 'komora:autoswap'

export function autoSwapGiven(): boolean {
  try {
    return localStorage.getItem(AUTOSWAP_KEY) === '1'
  } catch {
    return false
  }
}

export function rememberAutoSwap(given: boolean): void {
  try {
    localStorage.setItem(AUTOSWAP_KEY, given ? '1' : '0')
  } catch {
  }
}

export function forgetAutoSwap(): void {
  try {
    localStorage.removeItem(AUTOSWAP_KEY)
  } catch {
  }
}
