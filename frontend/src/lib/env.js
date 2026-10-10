/**
 * Environment configuration — validated once at boot (Phase 2 of docs/todo.md).
 *
 * Next.js inlines every `NEXT_PUBLIC_*` variable at build time. There are no
 * localhost fallbacks on purpose: a missing value must fail loudly with an
 * actionable message instead of silently pointing the app at a developer's
 * machine.
 *
 * Configure your machine with:  cp frontend/.env.example frontend/.env.local
 */

function fail(name, reason) {
  throw new Error(
    `[config] ${name} ${reason}.\n` +
      '  Fix: cd frontend && cp .env.example .env.local  (then edit the values)\n' +
      '  See frontend/.env.example for the full list of variables.'
  )
}

// Next.js only inlines *statically referenced* `process.env.NEXT_PUBLIC_*`
// values into the client bundle; a dynamic `process.env[name]` lookup yields
// `undefined` in the browser and blank-screens every page (caught by the
// Phase 4 Playwright suite). Snapshot the known keys statically first, then
// read through the snapshot.
const RAW_ENV = {
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL,
  NEXT_PUBLIC_SITE_NAME: process.env.NEXT_PUBLIC_SITE_NAME,
  NEXT_PUBLIC_ENABLE_SEARCH: process.env.NEXT_PUBLIC_ENABLE_SEARCH,
  NEXT_PUBLIC_ENABLE_2FA: process.env.NEXT_PUBLIC_ENABLE_2FA,
}

function requiredString(name) {
  const value = RAW_ENV[name]
  if (typeof value !== 'string' || value.trim() === '') {
    fail(name, 'is missing or empty')
  }
  return value.trim()
}

function optionalString(name, fallback) {
  const value = RAW_ENV[name]
  return typeof value === 'string' && value.trim() !== ''
    ? value.trim()
    : fallback
}

function optionalBool(name, fallback) {
  const value = RAW_ENV[name]
  if (value === undefined || value === '') return fallback
  const normalized = String(value).toLowerCase()
  if (['true', '1', 'yes', 'on'].includes(normalized)) return true
  if (['false', '0', 'no', 'off'].includes(normalized)) return false
  return fail(name, `must be a boolean (true/false), got "${value}"`)
}

/** Base URL of the Django API, e.g. `http://localhost:8000/api`. Required. */
export const API_URL = requiredString('NEXT_PUBLIC_API_URL')

/** Public origin of this site, used for canonical/OG tags (Phase 26). */
export const SITE_URL = optionalString(
  'NEXT_PUBLIC_SITE_URL',
  'http://localhost:3000'
)

/** Brand name shown in the header, titles and the footer. */
export const SITE_NAME = optionalString('NEXT_PUBLIC_SITE_NAME', 'MarketHub')

/** Feature flags — currently informational; enforced from Phase 15/7 onwards. */
export const ENABLE_SEARCH = optionalBool('NEXT_PUBLIC_ENABLE_SEARCH', true)
export const ENABLE_2FA = optionalBool('NEXT_PUBLIC_ENABLE_2FA', false)

const env = {
  API_URL,
  SITE_URL,
  SITE_NAME,
  ENABLE_SEARCH,
  ENABLE_2FA,
}

export default env
