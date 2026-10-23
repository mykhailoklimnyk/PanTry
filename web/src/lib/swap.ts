import { AUTO_SWAP_CAP_UAH } from './facts'
import { amount, uah } from './format'
import type { PriceFork } from './types'

export function forkRange(fork: PriceFork): string {
  return `від ${amount(fork.low, '')} до ${amount(fork.high, '₴')}${fork.per ? `/${fork.per}` : ''}`
}

export function forkBasis(price: number, fork: PriceFork): string {
  return `зараз ${uah(price)}${fork.per ? `/${fork.per}` : ''}`
}

export function forkNote(): string {
  return (
    'де є список замін — везуть за ним. ' +
    'Де ланцюжка немає — рівноцінна заміна того самого виду і в межах ціни цього рядка, ' +
    `не дорожче ніж на ${AUTO_SWAP_CAP_UAH} ₴; ` +
    'не знайдеться — не привезуть.'
  )
}
