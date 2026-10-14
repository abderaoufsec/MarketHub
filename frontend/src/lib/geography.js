/**
 * Wilaya/commune lookup — Phase 11 of docs/todo.md.
 *
 * The backend answers with per-request localized names (`name` follows the
 * `Accept-Language` header src/lib/api.js sends), so the picker never needs a
 * client-side dictionary. Results are cached in memory: a wilaya list is 69
 * rows that change once every few years, and a commune list is per-wilaya —
 * both survive a whole session, including language switches (the *names*
 * re-localize server-side, but the cached `name` field would go stale, so the
 * cache is keyed by locale too).
 */

import api from './api'
import { DEFAULT_LOCALE, LOCALE_COOKIE, isLocale } from '../i18n/config'

function currentLocale() {
  if (typeof document === 'undefined') return DEFAULT_LOCALE
  const match = document.cookie.match(
    new RegExp(`(?:^|\\s*;\\s*)${LOCALE_COOKIE}=([^;]*)`)
  )
  return isLocale(match ? decodeURIComponent(match[1]) : null)
    ? decodeURIComponent(match[1])
    : DEFAULT_LOCALE
}

const cache = { locale: null, wilayas: null, communes: new Map() }

function ensureLocale(locale) {
  if (cache.locale !== locale) {
    cache.locale = locale
    cache.wilayas = null
    cache.communes = new Map()
  }
}

/** All active wilayas (69), ordered by code. */
export async function fetchWilayas() {
  const locale = currentLocale()
  ensureLocale(locale)
  if (!cache.wilayas) {
    cache.wilayas = api
      .get('/geography/wilayas/')
      .then((response) => response.data)
      .catch((error) => {
        cache.wilayas = null // a failed fetch may be retried
        throw error
      })
  }
  return cache.wilayas
}

/** Communes of one wilaya (by wilaya id), optionally type-ahead filtered. */
export async function fetchCommunes(wilayaId, search = '') {
  const locale = currentLocale()
  ensureLocale(locale)
  const key = `${wilayaId}:${search}`
  if (!cache.communes.has(key)) {
    cache.communes.set(
      key,
      api
        .get(`/geography/wilayas/${wilayaId}/communes/`, {
          params: search ? { search } : {},
        })
        .then((response) => response.data)
        .catch((error) => {
          cache.communes.delete(key)
          throw error
        })
    )
  }
  return cache.communes.get(key)
}

/** Drop every cached row (used by tests and by nothing in production yet). */
export function clearGeographyCache() {
  cache.locale = null
  cache.wilayas = null
  cache.communes = new Map()
}
