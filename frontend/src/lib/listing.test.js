/**
 * `/l/<slug>-<id>` parsing (Phase 13 of docs/todo.md): the id is the only
 * durable part of the URL — the slug is regenerated on every rename, and the
 * page fetches by id alone.
 */
import { describe, expect, it } from 'vitest'

import { parseListingId } from './listing'

describe('parseListingId', () => {
  it('reads the trailing id out of a generated slug', () => {
    expect(parseListingId('velo-de-ville-123')).toBe(123)
  })

  it('takes the LAST -<digits> so digit-heavy titles keep their id', () => {
    // The API generates "<slugified-title>-<id>"; a title like "iPhone 15"
    // already ends in digits, so "iphone-15-77" is listing 77, not 15.
    expect(parseListingId('iphone-15-77')).toBe(77)
  })

  it('rejects segments without an id-shaped tail', () => {
    expect(parseListingId('velo-de-ville')).toBeNull()
    expect(parseListingId('just-a-slug')).toBeNull()
  })

  it('rejects empty or missing segments', () => {
    expect(parseListingId('')).toBeNull()
    expect(parseListingId(undefined)).toBeNull()
    expect(parseListingId(null)).toBeNull()
  })

  it('rejects impossible ids instead of querying the API with them', () => {
    expect(parseListingId('x-0')).toBeNull()
    // Beyond Number.MAX_SAFE_INTEGER this is not a real database id.
    expect(parseListingId('x-99999999999999999999')).toBeNull()
  })
})
