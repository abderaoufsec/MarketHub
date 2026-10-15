/**
 * lib/errors.js — the single reader for API failures (Phase 9 — Consistent
 * API contract, docs/todo.md).
 *
 * 1. **One envelope.** Every 4xx/5xx reply parses to
 *    `{status, code, message, details, requestId}`; nothing else may reach
 *    into `error.response.data`.
 * 2. **Legacy shapes still parse.** `{"error": …}`, `{"detail": …}`, a bare
 *   string body and a `{field: [messages]}` validation dict keep yielding a
 *    readable message instead of `undefined`.
 * 3. **No response at all** (CORS, offline, a dead proxy) is a
 *    `network_error` with the caller's fallback message.
 */
import { describe, expect, it } from 'vitest'

import {
  apiErrorMessage,
  apiFieldError,
  apiFieldErrors,
  parseApiError,
} from './errors'

/** The shape a rejected axios call hands us. */
const axiosError = (status, data, headers) => ({
  response: { status, data, headers },
})

describe('parseApiError — the Phase 9 envelope', () => {
  it('parses every field of the envelope', () => {
    const parsed = parseApiError(
      axiosError(400, {
        code: 'validation_error',
        message: 'Fix the form.',
        details: { email: ['A user with that email already exists.'] },
        request_id: 'req-123',
      })
    )

    expect(parsed).toEqual({
      status: 400,
      code: 'validation_error',
      message: 'Fix the form.',
      details: { email: ['A user with that email already exists.'] },
      requestId: 'req-123',
    })
  })

  it('falls back to the X-Request-ID header when the body has none', () => {
    const parsed = parseApiError(
      axiosError(
        429,
        { code: 'throttled', message: 'Too many requests.', details: null },
        { 'x-request-id': 'hdr-9' }
      )
    )

    expect(parsed.requestId).toBe('hdr-9')
    // Structured details survive for the 429 special-case (`details.wait`).
    expect(parsed.details).toBeNull()
    expect(parsed.status).toBe(429)
    expect(parsed.code).toBe('throttled')
  })

  it('re-parses an envelope that was already parsed', () => {
    // AuthContext hands parsed envelopes to its callers; the helpers must
    // accept them so `apiErrorMessage(result.error, …)` is not a trap.
    const envelope = {
      status: 401,
      code: 'invalid_credentials',
      message: 'Invalid credentials.',
      details: null,
      requestId: 'req-7',
    }

    expect(parseApiError(envelope)).toEqual(envelope)
    expect(apiErrorMessage(envelope)).toBe('Invalid credentials.')
    expect(apiFieldErrors(envelope)).toEqual({})
  })
})

describe('parseApiError — legacy bodies and the network', () => {
  it('reads the message out of the old {"error": …} body', () => {
    const parsed = parseApiError(
      axiosError(401, { error: 'Invalid credentials' })
    )

    expect(parsed).toEqual({
      status: 401,
      code: 'http_401',
      message: 'Invalid credentials',
      details: null,
      requestId: null,
    })
  })

  it('reads the message out of the old {"detail": …} body', () => {
    const parsed = parseApiError(axiosError(404, { detail: 'Not found.' }))

    expect(parsed.message).toBe('Not found.')
    expect(parsed.code).toBe('http_404')
    expect(parsed.details).toBeNull()
  })

  it('reads a bare string body (proxy/gateway replies)', () => {
    const parsed = parseApiError(axiosError(502, 'Bad gateway.'))

    expect(parsed.message).toBe('Bad gateway.')
    expect(parsed.code).toBe('http_502')
  })

  it('keeps a legacy validation dict as details so field errors still work', () => {
    const parsed = parseApiError(
      axiosError(400, {
        phone_number: ['This phone number is already registered.'],
      })
    )

    expect(parsed.code).toBe('validation_error')
    expect(parsed.message).toBe('This phone number is already registered.')
    expect(parsed.details).toEqual({
      phone_number: ['This phone number is already registered.'],
    })
    expect(apiFieldErrors(parsed)).toEqual({
      phone_number: ['This phone number is already registered.'],
    })
  })

  it('falls back to network_error with a usable message when nothing came back', () => {
    const parsed = parseApiError(new Error('Network Error'))

    expect(parsed).toEqual({
      status: null,
      code: 'network_error',
      message: 'Something went wrong.',
      details: null,
      requestId: null,
    })
    // The caller's own fallback is what reaches the user.
    expect(apiErrorMessage(new Error('Network Error'), 'Login failed')).toBe(
      'Login failed'
    )
  })

  it('never yields an empty message', () => {
    expect(apiErrorMessage(axiosError(500, {}))).toBe('Something went wrong.')
    expect(
      apiErrorMessage(axiosError(500, { message: '   ' }), 'Fallback')
    ).toBe('Fallback')
  })
})

describe('apiFieldErrors / apiFieldError', () => {
  const validationError = axiosError(400, {
    code: 'validation_error',
    message: 'Fix the form.',
    details: {
      email: ['A user with that email already exists.'],
      phone_number: ['This phone number is already registered.', 'Bad format.'],
    },
    request_id: 'req-5',
  })

  it('returns the details map of a validation_error', () => {
    expect(apiFieldErrors(validationError)).toEqual({
      email: ['A user with that email already exists.'],
      phone_number: ['This phone number is already registered.', 'Bad format.'],
    })
  })

  it('keeps a compound field’s per-key map (Phase 12 attributes_json)', () => {
    // The dynamic form highlights the offending input *by attribute key*,
    // so the nested map must survive normalisation instead of being
    // stringified or dropped as a non-list value.
    const dynamicFormError = axiosError(400, {
      code: 'validation_error',
      message: 'Fix the form.',
      details: {
        attributes_json: {
          km: ['Must be a number.'],
          bogus: ["Unknown attribute for 'cars'."],
        },
        category_id: ['A category is required.'],
      },
      request_id: 'req-7',
    })

    expect(apiFieldErrors(dynamicFormError)).toEqual({
      attributes_json: {
        km: ['Must be a number.'],
        bogus: ["Unknown attribute for 'cars'."],
      },
      category_id: ['A category is required.'],
    })
    // The compound field is a map, not a message list — the singular helper
    // answers null for it, and still returns the plain field's message.
    expect(apiFieldError(dynamicFormError, 'attributes_json')).toBeNull()
    expect(apiFieldError(dynamicFormError, 'category_id')).toBe(
      'A category is required.'
    )
  })

  it('returns {} when the failure carries no field messages', () => {
    expect(
      apiFieldErrors(
        axiosError(429, {
          code: 'throttled',
          message: 'Too many requests.',
          details: { wait: 30 },
          request_id: 'req-6',
        })
      )
    ).toEqual({})
    expect(apiFieldErrors(new Error('offline'))).toEqual({})
  })

  it('returns the first message for a known field, null for an unknown one', () => {
    expect(apiFieldError(validationError, 'phone_number')).toBe(
      'This phone number is already registered.'
    )
    expect(apiFieldError(validationError, 'username')).toBeNull()
    expect(apiFieldError(new Error('offline'), 'email')).toBeNull()
  })
})
