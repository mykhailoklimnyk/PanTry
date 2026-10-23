import { uahRound } from './format'
import type { DeliveryOption } from './types'

export function priceOf(option: DeliveryOption, known = true): string | null {
  const fee =
    option.serviceFee !== null && option.serviceFee > 0
      ? `збір ${uahRound(option.serviceFee)}`
      : null
  if (option.cost > 0) return fee ? `${uahRound(option.cost)} + ${fee}` : uahRound(option.cost)
  if (fee) return fee
  return known ? 'безкоштовно' : null
}
