// src/lib/env.js must read from a static snapshot of process.env: Next.js only
// inlines *statically referenced* NEXT_PUBLIC_* keys into the client bundle, so
// a dynamic `process.env[name]` lookup blank-screens every page (defect found
// by the Phase 4 Playwright suite — see docs/todo.md Phase 4 notes).
import { describe, it, expect, vi } from 'vitest'
import env, { API_URL, SITE_NAME } from '../lib/env'

describe('env config', () => {
  it('exposes the API URL from the environment', () => {
    // vitest.config.mjs sets test.env.NEXT_PUBLIC_API_URL
    expect(API_URL).toBe('http://api.test/api')
    expect(env.API_URL).toBe(API_URL)
  })

  it('falls back to defaults for optional values', () => {
    expect(SITE_NAME).toBeTruthy()
    expect(typeof env.ENABLE_SEARCH).toBe('boolean')
  })

  it('throws an actionable error for a missing required variable', async () => {
    // Simulate the "dynamic lookup" regression: with the key absent the module
    // must fail loudly rather than export undefined.
    vi.resetModules()
    const previous = process.env.NEXT_PUBLIC_API_URL
    delete process.env.NEXT_PUBLIC_API_URL
    try {
      await expect(import('../lib/env')).rejects.toThrow(/NEXT_PUBLIC_API_URL/)
    } finally {
      process.env.NEXT_PUBLIC_API_URL = previous
      vi.resetModules()
    }
  })
})
