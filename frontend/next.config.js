const createNextIntlPlugin = require('next-intl/plugin')

// Phase 11: registers src/i18n/request.js with next-intl's React Server
// layer (locale + messages for server renders; no i18n routing — the locale
// lives in the mh_locale cookie, see the request config's docstring).
const withNextIntl = createNextIntlPlugin('./src/i18n/request.js')

/**
 * Phase 14: only our own media may go through the image optimiser.
 *
 * Uploads are served from the API origin (Django's media view in dev, the
 * bucket/CDN in production). `next.config` is evaluated at build time, so the
 * list is derived from the public env vars the app already uses:
 *
 *   NEXT_PUBLIC_API_URL      http://localhost:8000/api/v1
 *   NEXT_PUBLIC_MEDIA_HOSTS  https://cdn.example.com,https://bucket.r2.dev
 *
 * External URLs on legacy listings still render (plain <img>, see
 * components/common/SafeImage.js), but `https://**` is no longer an open
 * proxy: an arbitrary host can never be resized through our server.
 */
function mediaPattern(raw) {
  try {
    const url = new URL(raw)
    const pattern = {
      protocol: url.protocol.replace(':', ''),
      hostname: url.hostname,
      pathname: '/media/**',
    }
    if (url.port) pattern.port = url.port
    return pattern
  } catch {
    return null
  }
}

const remotePatterns = []
const apiUrl = process.env.NEXT_PUBLIC_API_URL
if (apiUrl) {
  const pattern = mediaPattern(apiUrl)
  if (pattern) remotePatterns.push(pattern)
}
for (const host of (process.env.NEXT_PUBLIC_MEDIA_HOSTS || '').split(',')) {
  const trimmed = host.trim()
  if (!trimmed) continue
  const pattern = mediaPattern(trimmed.endsWith('/') ? trimmed : `${trimmed}/`)
  if (pattern) remotePatterns.push(pattern)
}
if (remotePatterns.length === 0) {
  // No env at build time (a lint/test build): the dev API origin only.
  remotePatterns.push({
    protocol: 'http',
    hostname: 'localhost',
    port: '8000',
    pathname: '/media/**',
  })
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns,
  },
  // NEXT_PUBLIC_* variables come straight from .env.* files and are inlined by
  // Next.js. No localhost fallback on purpose — src/lib/env.js validates them
  // at boot and fails with an actionable message when one is missing.
  // Improve build stability
  reactStrictMode: true,
  swcMinify: true,
  // Clear cache on build issues
  onDemandEntries: {
    maxInactiveAge: 25 * 1000,
    pagesBufferLength: 2,
  },
}

module.exports = withNextIntl(nextConfig)
