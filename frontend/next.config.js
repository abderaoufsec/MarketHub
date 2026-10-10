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

module.exports = nextConfig
