/**
 * `/l/<slug>-<id>` URL parsing (Phase 13 of docs/todo.md).
 *
 * The listing's id is the *only* durable part of the slug: the API generates
 * `<slugified-title>-<id>` on publish, and the page fetches by id alone — the
 * slug exists for humans and search engines, and a stale one (the ad was
 * renamed) is redirected to the canonical path by `<ProductDetail>`.
 *
 * Returns the numeric id, or null when the segment is not id-shaped (no
 * trailing `-<digits>`), so callers can answer 404 instead of querying the
 * API with `NaN`.
 */
export function parseListingId(slugId) {
  const match = /^(.+)-(\d+)$/.exec(slugId || '')
  if (!match) return null
  const id = Number(match[2])
  return Number.isSafeInteger(id) && id > 0 ? id : null
}
