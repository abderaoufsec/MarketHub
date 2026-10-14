/**
 * Render helper: wraps a component in the same providers the root layout
 * supplies in production (Phase 11 of docs/todo.md).
 *
 * Components call `useTranslations`/`useLocale` (next-intl) and `usePrice`
 * (src/lib/currency), which all need a `NextIntlClientProvider`. Unit tests
 * render with English by default — the E2E suite pins the same default by
 * setting the `mh_locale=en` cookie — and assert against the English message
 * catalogue, so a translation regression shows up as a broken string.
 */

import { render } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import en from '../i18n/messages/en.json'
import fr from '../i18n/messages/fr.json'
import ar from '../i18n/messages/ar.json'

const MESSAGES = { en, fr, ar }

export function renderWithIntl(ui, { locale = 'en', ...options } = {}) {
  return render(ui, {
    wrapper: ({ children }) => (
      <NextIntlClientProvider
        locale={locale}
        messages={MESSAGES[locale]}
        timeZone="Africa/Algiers"
        onError={(error) => {
          // next-intl logs "MISSING_MESSAGE" noise for intentionally missing
          // keys during tests; real errors must still fail loudly.
          if (error.code !== 'MISSING_MESSAGE') throw error
        }}
      >
        {children}
      </NextIntlClientProvider>
    ),
    ...options,
  })
}

export default renderWithIntl
