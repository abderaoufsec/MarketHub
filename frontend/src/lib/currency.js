/**
 * DZD price display — Phase 11 of docs/todo.md.
 *
 * Algeria prices in **dinars**, but two habits coexist:
 *
 * - **standard** — `45 000 DZD`, what a listing page shows;
 * - **millions** — the colloquial *centimes* habit: `1 million` = 10 000 DA
 *   (1 DA = 100 centimes, so 1 000 000 centimes = 10 000 DA). A car quoted
 *   "250 millions" is 2 500 000 DA. Both are legitimate, so the display is a
 *   preference (cookie `mh_price_display`), not a hard-coded choice.
 *
 * `formatPrice` is **pure**: locale and display mode arrive as arguments, read
 * by the caller (the `usePrice` hook), so server and client always format the
 * same way — reading cookies at render time would hydrate `fr` text over a
 * client `en` cookie and warn. The cookie itself is read once on the client
 * through `useSyncExternalStore` (server snapshot: `standard`), which is the
 * hydration-safe pattern: React re-renders after mount when they differ.
 *
 * Arabic numerals: `ar-DZ` (see `i18n/config.js`) — the Maghreb writes
 * Western digits, so `٠١٢٣` never appears in an Algerian UI.
 */

import { useSyncExternalStore } from 'react'
import { useLocale } from 'next-intl'
import { DEFAULT_LOCALE, PRICE_COOKIE, intlLocale } from '../i18n/config'

/** 1 "million" (centimes) = 10 000 DA — see the module docstring. */
export const MILLIONS_DIVISOR = 10000

export const PRICE_DISPLAY_MODES = ['standard', 'millions']

function readCookie(name) {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(
    new RegExp(`(?:^|\\s*;\\s*)${name}=([^;]*)`)
  )
  return match ? decodeURIComponent(match[1]) : null
}

/** Current display mode: 'standard' | 'millions' (client), 'standard' on the server. */
export function getPriceDisplay() {
  const value = readCookie(PRICE_COOKIE)
  return PRICE_DISPLAY_MODES.includes(value) ? value : 'standard'
}

const listeners = new Set()

export function subscribePriceDisplay(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Persist the display preference and notify every mounted `usePrice`. */
export function setPriceDisplay(mode) {
  const value = PRICE_DISPLAY_MODES.includes(mode) ? mode : 'standard'
  if (typeof document !== 'undefined') {
    document.cookie = `${PRICE_COOKIE}=${encodeURIComponent(value)}; path=/; max-age=31536000; SameSite=Lax`
  }
  listeners.forEach((listener) => listener())
  return value
}

const SUFFIX = {
  // Singular below 2 — "1.5 million" reads singular in both English and
  // French, while "2 millions" is plural.
  fr: (n) => (Math.abs(n) < 2 ? 'million' : 'millions'),
  en: (n) => (Math.abs(n) < 2 ? 'million' : 'millions'),
  // Arabic plurals: dual/small plural 2–10 gets ملايين, everything else
  // (including 250 and 0.5) gets المليون-style singular.
  ar: (n) => (n >= 2 && n <= 10 ? 'ملايين' : 'مليون'),
}

function integerPartIsWhole(value) {
  return Number.isInteger(Number(value))
}

/**
 * Format a DZD amount.
 *
 * @param {number|string} value — price in dinars (45000, '45000.5')
 * @param {object} [opts]
 * @param {string} [opts.locale='fr'] — UI locale (fr | ar | en)
 * @param {'standard'|'millions'} [opts.display='standard']
 * @returns {string}
 */
export function formatPrice(value, opts = {}) {
  const { locale = DEFAULT_LOCALE, display = 'standard' } = opts
  const numeric = Number(value)
  const amount = Number.isNaN(numeric) ? 0 : numeric

  if (display === 'millions') {
    const millions = amount / MILLIONS_DIVISOR
    const number = new Intl.NumberFormat(intlLocale(locale), {
      maximumFractionDigits: 2,
    }).format(millions)
    const suffix = (SUFFIX[locale] || SUFFIX.en)(millions)
    return `${number} ${suffix}`
  }

  // Whole dinars show no decimals ("45 000 DZD"); anything with a fraction
  // gets two ("45 000,50 DZD") — cents exist in the data model, so they must
  // never vanish, but padding every whole price with ",00" is noise.
  return new Intl.NumberFormat(intlLocale(locale), {
    style: 'currency',
    currency: 'DZD',
    minimumFractionDigits:
      integerPartIsWhole(amount) && amount % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(amount)
}

/**
 * React binding: locale comes from the server-rendered `NextIntlClientProvider`
 * (hydration-safe), display mode from the cookie via `useSyncExternalStore`.
 *
 * @returns {(value: number|string, opts?: object) => string}
 */
export function usePrice() {
  const locale = useLocale()
  const display = useSyncExternalStore(
    subscribePriceDisplay,
    getPriceDisplay,
    () => 'standard'
  )
  return (value, opts = {}) => formatPrice(value, { locale, display, ...opts })
}

export default formatPrice
