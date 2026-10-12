/**
 * The single reader for API failures (Phase 9 — Consistent API contract,
 * docs/todo.md).
 *
 * Since Phase 9 every 4xx/5xx reply is one envelope:
 *
 *   {"code": "invalid_credentials", "message": "Invalid credentials.",
 *    "details": null, "request_id": "8f14e45f…"}
 *
 * Components must not reach into `error.response.data` themselves: they ask
 * this module for a message to show, for field messages to render, or for the
 * parsed envelope to branch on (`code`, `status`, `details`).
 *
 * The legacy shapes are still understood so nothing degrades to `undefined`
 * while the backend rolls out or when a proxy answers instead of Django:
 *   - `{"error": "…"}` / `{"detail": "…"}` (the pre-Phase-9 error bodies),
 *   - a bare string body (some gateways),
 *   - a `{field: [messages]}` validation dict (DRF serializer errors),
 *   - no response at all (CORS, offline, DNS) → `network_error`.
 *
 * Success (2xx) bodies are *not* handled here — some of them legitimately use
 * `{"detail": …}` or `{"message": …}` and are read directly by the caller.
 */

/** Message used when the payload (or the network) says nothing usable. */
const DEFAULT_MESSAGE = 'Something went wrong.'

/**
 * Body keys that carry their own meaning: when one of them holds a *string*
 * the body is a scalar error, not a `{field: [messages]}` validation dict.
 * (A field literally named `code` — the OTP endpoints — passes as an array.)
 */
const SCALAR_KEYS = [
  'code',
  'error',
  'message',
  'detail',
  'request_id',
  'requestId',
]

function isText(value) {
  return typeof value === 'string' && value.trim() !== ''
}

function isPlainObject(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return false
  }
  // Strict on purpose: an `Error` (axios failures, network errors) carries its
  // own English `message` and must never be mistaken for a response body.
  const proto = Object.getPrototypeOf(value)
  return proto === null || proto === Object.prototype
}

/** First usable string inside a message / list-of-messages value, else null. */
function firstText(value) {
  if (isText(value)) return value
  if (Array.isArray(value)) {
    for (const item of value) {
      const text = firstText(item)
      if (text !== null) return text
    }
  }
  return null
}

/** `{field: [messages]}` — a DRF serializer body (or its plain-string form). */
function isFieldDict(body) {
  if (!isPlainObject(body)) return false
  const entries = Object.entries(body)
  if (entries.length === 0) return false
  if (
    entries.some(([key, value]) => SCALAR_KEYS.includes(key) && isText(value))
  ) {
    return false
  }
  return entries.every(([, value]) =>
    Array.isArray(value) ? value.some(isText) : isText(value)
  )
}

/** A Phase 9 envelope (or one of the pre-rollout hybrids that already had `code`). */
function isEnvelope(body) {
  if (!isPlainObject(body)) return false
  return isText(body.code) || 'request_id' in body || 'requestId' in body
}

function pickStatus(response, error) {
  if (response && typeof response.status === 'number') return response.status
  // Also accepts an envelope handed back to a caller (AuthContext) directly.
  if (isPlainObject(error) && typeof error.status === 'number')
    return error.status
  return null
}

function pickCode(body, status) {
  if (isEnvelope(body)) return body.code
  // The field dict is what a 400 from a serializer looks like — classify it
  // even when it arrives without an HTTP status (a re-parsed envelope).
  if (isFieldDict(body)) return 'validation_error'
  if (status === null) return 'network_error' // no reply at all: CORS/offline
  if (status === 429) return 'throttled' // legacy throttle bodies: `{"detail": …}`
  return `http_${status}` // stable, but branch on the status itself
}

function pickMessage(body, fallback) {
  if (isText(body)) return body
  if (isPlainObject(body)) {
    // Envelope first, then the legacy scalar keys (bodies that had a `code`
    // but still kept their text in `error`/`detail`).
    const candidate =
      firstText(body.message) ?? firstText(body.error) ?? firstText(body.detail)
    if (candidate !== null) return candidate
    if (isFieldDict(body)) {
      // Show something specific ("This phone number is already registered.")
      // rather than a generic fallback: the catch-all first, else the first field.
      return (
        firstText(body.non_field_errors) ?? firstText(Object.values(body)[0])
      )
    }
  }
  return fallback
}

function pickDetails(body) {
  if (isEnvelope(body)) {
    return isPlainObject(body.details) || Array.isArray(body.details)
      ? body.details
      : null
  }
  // Legacy validation dict: keep it as `details` so `apiFieldErrors` still
  // works against a backend that has not rolled the envelope out yet.
  return isFieldDict(body) ? body : null
}

function pickRequestId(body, response) {
  if (isPlainObject(body)) {
    if (isText(body.request_id)) return body.request_id
    if (isText(body.requestId)) return body.requestId
  }
  // The header carries the same value as the body field (Phase 9 contract).
  const headers = response?.headers
  if (headers) {
    const fromGetter =
      typeof headers.get === 'function' ? headers.get('X-Request-ID') : null
    const direct = headers['x-request-id'] ?? headers['X-Request-ID']
    return firstText(fromGetter) ?? firstText(direct)
  }
  return null
}

/**
 * Normalise any axios failure into the Phase 9 envelope.
 *
 * Accepts an axios error, a bare `Error` (network/CORS), or an envelope that
 * was already parsed (so a value stored by AuthContext round-trips unchanged).
 */
function normalize(error, fallback) {
  // An axios failure keeps the reply on `error.response`; anything else is
  // treated as the body itself when it is a plain object.
  const response =
    error && typeof error === 'object' && 'response' in error
      ? error.response
      : null
  const body = response ? response.data : isPlainObject(error) ? error : null
  const status = pickStatus(response, error)

  return {
    status,
    code: pickCode(body, status),
    message: pickMessage(body, fallback),
    details: pickDetails(body),
    requestId: pickRequestId(body, response),
  }
}

/** Normalise any axios failure into the Phase 9 envelope. */
export function parseApiError(error) {
  return normalize(error, DEFAULT_MESSAGE)
}

/**
 * The text to show the user: the payload's `message` when there is one,
 * otherwise `fallback` — never an empty string.
 */
export function apiErrorMessage(error, fallback = DEFAULT_MESSAGE) {
  return normalize(error, fallback).message
}

/**
 * Field → messages map for a `validation_error` (`details`), normalised to
 * lists of strings. `{}` when the failure carries no field-level messages.
 */
export function apiFieldErrors(error) {
  const { code, details } = parseApiError(error)
  if (code !== 'validation_error' || !isPlainObject(details)) return {}

  const fields = {}
  for (const [field, messages] of Object.entries(details)) {
    const list = (Array.isArray(messages) ? messages : [messages]).filter(
      isText
    )
    if (list.length > 0) fields[field] = list
  }
  return fields
}

/** First message for `field`, or null when that field has none. */
export function apiFieldError(error, field) {
  const messages = apiFieldErrors(error)[field]
  return messages && messages.length > 0 ? messages[0] : null
}
