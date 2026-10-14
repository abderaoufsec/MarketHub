// Shared Playwright fixture — Phase 11 of docs/todo.md.
//
// The app's default locale is French (Algerian launch market), but the smoke
// specs were written against the English catalogue. Pin the locale with the
// same `mh_locale` cookie the header switcher writes, once per context, so
// every spec sees a deterministic English/LTR UI — and incidentally exercises
// the cookie-based locale path end-to-end.
const base = require('@playwright/test')

const FRONTEND_URL = process.env.E2E_FRONTEND_URL || 'http://localhost:3000'

const test = base.test.extend({
  context: async ({ context }, use) => {
    await context.addCookies([
      { name: 'mh_locale', value: 'en', url: FRONTEND_URL },
    ])
    await use(context)
  },
})

module.exports = { test, expect: base.expect }
