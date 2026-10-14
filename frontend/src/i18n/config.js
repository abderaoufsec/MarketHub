/**
 * Locale configuration — Phase 11 of docs/todo.md (Algeria localisation).
 *
 * There is deliberately **no `/<lang>/` URL segment** yet: that is Phase 26's
 * SEO work. The locale lives in a cookie (`mh_locale`), so every URL keeps
 * working in all three languages and switching language is a refresh, not a
 * navigation. The root layout reads the cookie server-side and sets
 * `<html lang dir>` before first paint — no client-side flash.
 *
 * Default is `fr`: the launch market is Algeria and the backend's own
 * `LANGUAGE_CODE` is `fr`, so a first-time visitor without a cookie sees the
 * same language the API would answer in.
 */

export const LOCALES = ['fr', 'ar', 'en']

/** Locale used when no (or an invalid) `mh_locale` cookie is present. */
export const DEFAULT_LOCALE = 'fr'

/** Cookie the LanguageSwitcher writes; read by the root layout. */
export const LOCALE_COOKIE = 'mh_locale'

/** Cookie holding the price-display preference: 'standard' | 'millions'. */
export const PRICE_COOKIE = 'mh_price_display'

/** Text direction per locale — only Arabic reads right-to-left. */
export const DIRECTIONS = { fr: 'ltr', en: 'ltr', ar: 'rtl' }

export function isLocale(value) {
  return typeof value === 'string' && LOCALES.includes(value)
}

export function resolveLocale(value) {
  return isLocale(value) ? value : DEFAULT_LOCALE
}

export function dirFor(locale) {
  return DIRECTIONS[resolveLocale(locale)] || 'ltr'
}

/**
 * BCP-47 tag handed to `Intl` for a UI locale.
 *
 * `ar` alone would give Eastern digits (٠١٢٣) through `arab` numbering — but
 * the Maghreb writes numbers with Western digits (0123), which is what
 * `ar-DZ` resolves to. `fr` and `en` already map to their default regions.
 */
export const INTL_LOCALES = { fr: 'fr', en: 'en', ar: 'ar-DZ' }

export function intlLocale(locale) {
  return INTL_LOCALES[resolveLocale(locale)] || DEFAULT_LOCALE
}

const config = {
  LOCALES,
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  PRICE_COOKIE,
  DIRECTIONS,
  isLocale,
  resolveLocale,
  dirFor,
  intlLocale,
}

export default config
