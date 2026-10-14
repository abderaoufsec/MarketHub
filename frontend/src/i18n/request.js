/**
 * next-intl request config — Phase 11 of docs/todo.md ("without i18n
 * routing" setup).
 *
 * next-intl's React Server layer — the RSC build of `NextIntlClientProvider`,
 * `getTranslations`, … — resolves the locale and messages through the module
 * this plugin registers. Without it every *server* render throws "Couldn't
 * find next-intl config file". The unit suite cannot catch that: vitest
 * resolves the client build of next-intl, which reads the props the root
 * layout passes instead. `next dev`/`next start` are the judges here.
 *
 * Deliberately no `/<lang>/` segment (that is Phase 26's SEO work): the
 * locale is the same `mh_locale` cookie the root layout reads for
 * `<html lang dir>`, so the two can never disagree.
 */
import { getRequestConfig } from 'next-intl/server'
import { cookies } from 'next/headers'
import { LOCALE_COOKIE, resolveLocale } from './config'
import en from './messages/en.json'
import fr from './messages/fr.json'
import ar from './messages/ar.json'

const MESSAGES = { en, fr, ar }

export default getRequestConfig(async () => {
  const locale = resolveLocale(cookies().get(LOCALE_COOKIE)?.value)
  return {
    locale,
    messages: MESSAGES[locale],
    timeZone: 'Africa/Algiers',
  }
})
