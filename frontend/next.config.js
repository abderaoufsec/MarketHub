const createNextIntlPlugin = require('next-intl/plugin')

// Phase 11: registers src/i18n/request.js with next-intl's React Server
// layer (locale + messages for server renders; no i18n routing — the locale
// lives in the mh_locale cookie, see the request config's docstring).
const withNextIntl = createNextIntlPlugin('./src/i18n/request.js')

/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**',
      },
      {
        protocol: 'http',
        hostname: 'localhost',
        port: '8000',
      },
    ],
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
