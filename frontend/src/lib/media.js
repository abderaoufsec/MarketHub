import { API_URL, MEDIA_HOSTS } from './env'

/**
 * Phase 14: which image hosts `next/image` is allowed to optimise.
 *
 * Uploads are served by the API origin in development (Django's media view)
 * and by the bucket/CDN in production. The same list feeds
 * `next.config.js`'s `remotePatterns`, so a URL that renders here is one the
 * optimiser will accept — and nothing else is: `https://**` is gone.
 *
 * Anything else (a legacy listing that still points at an external URL) is
 * rendered with a plain `<img>`: the API accepts those URLs, so the UI must
 * show them, but they must not become an open image proxy.
 */

/** `http://localhost:8000/api/v1` -> `http://localhost:8000`. */
export const API_ORIGIN = API_URL.replace(/\/api\/v\d+\/?$/, '')

export function canOptimizeImage(url) {
  if (!url || typeof url !== 'string') return false
  if (url.startsWith('/')) return true
  if (!/^https?:\/\//i.test(url)) return false
  try {
    const { origin } = new URL(url)
    return origin === API_ORIGIN || MEDIA_HOSTS.includes(origin)
  } catch {
    return false
  }
}

export function isRemoteImage(url) {
  return typeof url === 'string' && /^https?:\/\//i.test(url)
}
