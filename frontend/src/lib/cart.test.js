import { describe, expect, it } from 'vitest'

import { cartItemCount, cartSubtotal, formatPrice, lineTotal } from './cart'

describe('lineTotal', () => {
  it('multiplies unit price by quantity', () => {
    expect(
      lineTotal({ price_at_time_of_addition: '100.00', quantity: 3 })
    ).toBe(300)
  })

  it('handles decimal prices', () => {
    expect(
      lineTotal({ price_at_time_of_addition: '199.50', quantity: 2 })
    ).toBe(399)
  })

  it('returns 0 for missing or invalid input', () => {
    expect(lineTotal(null)).toBe(0)
    expect(lineTotal(undefined)).toBe(0)
    expect(lineTotal({})).toBe(0)
    expect(lineTotal({ price_at_time_of_addition: 'abc', quantity: 2 })).toBe(0)
  })

  it('treats a missing quantity as 0', () => {
    expect(lineTotal({ price_at_time_of_addition: '100.00' })).toBe(0)
  })
})

describe('cartSubtotal', () => {
  it('sums every line total', () => {
    const items = [
      { price_at_time_of_addition: '100.00', quantity: 2 },
      { price_at_time_of_addition: '25.50', quantity: 1 },
    ]
    expect(cartSubtotal(items)).toBe(225.5)
  })

  it('is 0 for an empty cart', () => {
    expect(cartSubtotal([])).toBe(0)
  })

  it('is 0 when cart is null/undefined (pre-load state)', () => {
    expect(cartSubtotal(null)).toBe(0)
    expect(cartSubtotal(undefined)).toBe(0)
  })

  it('does not silently produce NaN for bad rows', () => {
    const items = [
      { price_at_time_of_addition: '100.00', quantity: 1 },
      { price_at_time_of_addition: null, quantity: 2 },
    ]
    expect(cartSubtotal(items)).toBe(100)
  })
})

describe('cartItemCount', () => {
  it('sums quantities, not lines', () => {
    const items = [
      { price_at_time_of_addition: '10.00', quantity: 5 },
      { price_at_time_of_addition: '20.00', quantity: 1 },
    ]
    expect(cartItemCount(items)).toBe(6)
  })

  it('is 0 for empty or missing carts', () => {
    expect(cartItemCount([])).toBe(0)
    expect(cartItemCount(null)).toBe(0)
  })
})

describe('formatPrice', () => {
  it('renders two decimals with a currency symbol', () => {
    expect(formatPrice(19900)).toBe('$19900.00')
    expect(formatPrice('45000.5')).toBe('$45000.50')
  })

  it('falls back to $0.00 for invalid amounts', () => {
    expect(formatPrice(undefined)).toBe('$0.00')
    expect(formatPrice('not-a-price')).toBe('$0.00')
  })
})
