/**
 * Category tree + attribute definitions — Phase 12 of docs/todo.md.
 *
 * The backend answers with per-request localized names/labels (`name` and
 * `label` follow the `Accept-Language` header src/lib/api.js sends), so this
 * module never translates anything itself: it fetches the tree once per
 * session and lets components read `label`/`name` directly. The cache is
 * keyed by locale (like src/lib/geography.js) — switching language re-fetches
 * because the *localized fields* would otherwise go stale.
 *
 * The tree is small (tens of nodes, one call), but forms need lookups by id
 * and by slug, and the products filter needs a flat list with depth for
 * indentation — those are derived once per fetch, not per render.
 */

import api from './api'
import { DEFAULT_LOCALE, LOCALE_COOKIE, isLocale } from '../i18n/config'

function currentLocale() {
  if (typeof document === 'undefined') return DEFAULT_LOCALE
  const match = document.cookie.match(
    new RegExp(`(?:^|\\s*;)\\s*${LOCALE_COOKIE}=([^;]*)`)
  )
  return isLocale(match ? decodeURIComponent(match[1]) : null)
    ? decodeURIComponent(match[1])
    : DEFAULT_LOCALE
}

const cache = { locale: null, tree: null, byId: null, bySlug: null, flat: null }

/**
 * The active root categories (nested, as served).
 * Resolves to an array — never null — so callers can map immediately.
 */
export async function fetchCategoryTree() {
  const locale = currentLocale()
  if (cache.locale !== locale) {
    cache.locale = locale
    cache.tree = null
    cache.byId = null
    cache.bySlug = null
    cache.flat = null
  }
  if (!cache.tree) {
    cache.tree = api
      .get('/catalog/categories/')
      .then((response) => {
        const tree = response.data
        index(tree)
        return tree
      })
      .catch((error) => {
        cache.tree = null // a failed fetch may be retried
        throw error
      })
  }
  return cache.tree
}

function index(tree) {
  const byId = new Map()
  const bySlug = new Map()
  const flat = []

  const walk = (nodes, depth, parentId) => {
    for (const node of nodes) {
      const entry = { ...node, depth, parentId }
      byId.set(node.id, entry)
      bySlug.set(node.slug, entry)
      flat.push(entry)
      if (node.children?.length) walk(node.children, depth + 1, node.id)
    }
  }
  walk(tree, 0, null)

  cache.byId = byId
  cache.bySlug = bySlug
  cache.flat = flat
}

/** Node by id (or undefined before the tree loads / for unknown ids). */
export function categoryById(id) {
  return cache.byId?.get(Number(id))
}

/** Node by slug — the `?category=` filter value. */
export function categoryBySlug(slug) {
  return cache.bySlug?.get(slug)
}

/**
 * Every node flattened depth-first with `depth` for indented selects.
 * Only nodes on an *active path* reach the API (inactive children are
 * dropped server-side), so nothing needs filtering here.
 */
export function flatCategories() {
  return cache.flat ?? []
}

/**
 * The attribute definitions a node's form must render: its own plus every
 * ancestor's, deeper overriding on key collision — the client-side twin of
 * `Category.effective_attribute_definitions`, applied from the tree so the
 * form needs no second call.
 */
export function effectiveDefinitions(categoryId) {
  const node = categoryById(categoryId)
  if (!node) return []

  const chain = []
  for (let current = node; current; current = categoryById(current.parentId)) {
    chain.push(current)
  }
  // Shallow first so deeper definitions overwrite on key collision.
  const byKey = new Map()
  for (const ancestor of chain.reverse()) {
    for (const definition of ancestor.attribute_definitions ?? []) {
      byKey.set(definition.key, definition)
    }
  }
  return [...byKey.values()].sort(
    (a, b) => a.order - b.order || a.key.localeCompare(b.key)
  )
}

/** Drop every cached row (used by tests and by nothing in production yet). */
export function clearCatalogCache() {
  cache.locale = null
  cache.tree = null
  cache.byId = null
  cache.bySlug = null
  cache.flat = null
}
