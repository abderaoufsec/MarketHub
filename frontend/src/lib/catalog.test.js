/**
 * Category tree helpers — Phase 12 of docs/todo.md.
 *
 * `effectiveDefinitions` is the client-side twin of the backend's
 * `Category.effective_attribute_definitions`: the edit/filter forms render
 * from it, so ancestor inheritance and the "deeper definition wins" rule
 * have to hold here too, or the form would ask for fields the API doesn't
 * validate (or miss ones it does).
 *
 * The tree fetch mirrors src/lib/geography.js: one request per session,
 * indexed once for id/slug/depth lookups.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({
  default: { get: vi.fn() },
}))

import api from './api'
import {
  categoryById,
  categoryBySlug,
  clearCatalogCache,
  effectiveDefinitions,
  fetchCategoryTree,
  flatCategories,
} from './catalog'

const TREE = [
  {
    id: 1,
    slug: 'vehicles',
    name: 'Véhicules',
    attribute_definitions: [
      { key: 'brand', label: 'Marque', type: 'enum', order: 5 },
      { key: 'year', label: 'Année', type: 'number', order: 10 },
    ],
    children: [
      {
        id: 2,
        slug: 'cars',
        name: 'Voitures',
        // The child redefines `year` (deeper wins) and adds `mileage`.
        attribute_definitions: [
          { key: 'year', label: 'Année (child)', type: 'year', order: 10 },
          { key: 'mileage', label: 'Kilométrage', type: 'number', order: 20 },
        ],
        children: [],
      },
    ],
  },
  {
    id: 9,
    slug: 'jobs',
    name: 'Emplois',
    attribute_definitions: [],
    children: [],
  },
]

describe('catalog tree', () => {
  beforeEach(() => {
    clearCatalogCache()
    api.get.mockReset()
    api.get.mockResolvedValue({ data: TREE })
  })

  it('fetches the tree once per session and caches the promise', async () => {
    const first = await fetchCategoryTree()
    const second = await fetchCategoryTree()

    expect(api.get).toHaveBeenCalledTimes(1)
    expect(api.get).toHaveBeenCalledWith('/catalog/categories/')
    expect(first).toEqual(TREE)
    expect(second).toEqual(TREE)
  })

  it('refetches after the cache is cleared', async () => {
    await fetchCategoryTree()
    clearCatalogCache()
    await fetchCategoryTree()

    expect(api.get).toHaveBeenCalledTimes(2)
  })

  it('indexes nodes by id and slug with depth-first order', async () => {
    await fetchCategoryTree()

    expect(categoryById(1).slug).toBe('vehicles')
    expect(categoryBySlug('jobs').id).toBe(9)

    const cars = categoryBySlug('cars')
    expect(cars.depth).toBe(1)
    expect(cars.parentId).toBe(1)

    expect(flatCategories().map((node) => node.slug)).toEqual([
      'vehicles',
      'cars',
      'jobs',
    ])
    expect(flatCategories().map((node) => node.depth)).toEqual([0, 1, 0])
  })

  it('inherits ancestor definitions, deeper winning on key collision', async () => {
    await fetchCategoryTree()

    const definitions = effectiveDefinitions(2)
    expect(definitions.map((definition) => definition.key)).toEqual([
      'brand', // inherited from vehicles (order 5)
      'year', // child's own definition, not the parent's
      'mileage', // declared on cars (order 20)
    ])
    // Deeper override: the child's year, re-typed and re-labelled.
    const year = definitions.find((definition) => definition.key === 'year')
    expect(year.type).toBe('year')
    expect(year.label).toBe('Année (child)')
  })

  it('returns the node’s own definitions when there is no ancestor', async () => {
    await fetchCategoryTree()

    expect(effectiveDefinitions(9)).toEqual([])
    expect(effectiveDefinitions(null)).toEqual([])
    expect(effectiveDefinitions(404)).toEqual([])
  })
})
