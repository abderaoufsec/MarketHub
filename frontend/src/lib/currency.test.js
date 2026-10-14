/**
 * DZD formatting — Phase 11 of docs/todo.md.
 *
 * Assertions deliberately normalize Unicode spaces before comparing: ICU's
 * group separators (U+202F narrow no-break space in `fr`) vary between Node
 * builds, and matching invisible characters would test the ICU table, not our
 * rules. What these tests pin is *our* contract: whole dinars without cents,
 * two decimals when there are cents, the "millions" centimes convention, and
 * Western digits for Arabic (the Maghreb writes ٠١٢٣ never).
 */

import { afterEach, describe, expect, it } from 'vitest'
import {
  MILLIONS_DIVISOR,
  formatPrice,
  getPriceDisplay,
  setPriceDisplay,
} from './currency'
import { PRICE_COOKIE } from '../i18n/config'

/** Drop every kind of space so "45 000 DZD" === "45000DZD". */
const squash = (value) => value.replace(/\s/g, '')

afterEach(() => {
  document.cookie = `${PRICE_COOKIE}=; path=/; max-age=0`
})

describe('formatPrice (standard DZD)', () => {
  it('formats whole dinars without cents, grouped', () => {
    expect(squash(formatPrice(45000, { locale: 'fr' }))).toBe('45000DZD')
    expect(squash(formatPrice('19900', { locale: 'fr' }))).toBe('19900DZD')
  })

  it('keeps two decimals when the amount has cents', () => {
    expect(squash(formatPrice('45000.5', { locale: 'fr' }))).toBe(
      '45000,50DZD' // fr decimal comma
    )
    expect(squash(formatPrice(45000.5, { locale: 'en' }))).toBe(
      'DZD45,000.50' // en decimal point, currency up front
    )
  })

  it('falls back to 0 DZD for invalid amounts', () => {
    expect(squash(formatPrice(undefined, { locale: 'fr' }))).toBe('0DZD')
    expect(squash(formatPrice('not-a-price', { locale: 'fr' }))).toBe('0DZD')
  })

  it('defaults to French when no locale is given', () => {
    expect(squash(formatPrice(45000))).toBe('45000DZD')
  })
})

describe('Arabic numerals (Phase 11: Eastern/Western digit handling)', () => {
  it('uses Western digits for ar — the Maghreb convention', () => {
    const rendered = formatPrice(45000, { locale: 'ar' })
    expect(rendered).toContain('45')
    expect(rendered).not.toMatch(/[٠-٩]/) // no Arabic-Indic digits
    expect(rendered).toContain('د.ج') // the local symbol, not "DZD"
  })
})

describe('formatPrice (millions / centimes mode)', () => {
  it('converts dinars to centime-millions (1 million = 10 000 DA)', () => {
    expect(MILLIONS_DIVISOR).toBe(10000)
    expect(formatPrice(10000, { locale: 'en', display: 'millions' })).toBe(
      '1 million'
    )
    expect(formatPrice(2500000, { locale: 'en', display: 'millions' })).toBe(
      '250 millions'
    )
  })

  it('pluralizes per language', () => {
    expect(formatPrice(10000, { locale: 'fr', display: 'millions' })).toBe(
      '1 million'
    )
    expect(formatPrice(20000, { locale: 'fr', display: 'millions' })).toBe(
      '2 millions'
    )
    expect(formatPrice(10000, { locale: 'ar', display: 'millions' })).toBe(
      '1 مليون'
    )
    expect(formatPrice(50000, { locale: 'ar', display: 'millions' })).toBe(
      '5 ملايين'
    )
  })

  it('shows a fractional million with at most two decimals', () => {
    expect(formatPrice(15000, { locale: 'en', display: 'millions' })).toBe(
      '1.5 million'
    )
  })
})

describe('price display preference (cookie)', () => {
  it('is "standard" with no cookie', () => {
    expect(getPriceDisplay()).toBe('standard')
  })

  it('round-trips through the cookie and ignores invalid values', () => {
    setPriceDisplay('millions')
    expect(getPriceDisplay()).toBe('millions')
    document.cookie = `${PRICE_COOKIE}=nonsense; path=/`
    expect(getPriceDisplay()).toBe('standard')
  })
})
