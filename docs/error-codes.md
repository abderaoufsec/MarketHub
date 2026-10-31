# API Error Codes

> **Phase 9 deliverable.** The machine-readable half of the API contract.
> Everything under `/api/v1/` answers a failure with one envelope; this page
> is the reference for what `code` can say. The human half — the sentence in
> `message` — is covered in [`README.md`](README.md) and is translated per
> `Accept-Language` (en/fr/ar).

`backend/tests/test_error_codes_doc.py` ratchets this file against the source:
a new error code cannot ship without an entry here, and an entry cannot
describe a code the API no longer emits.

---

## 1. The envelope

Every response with a status of **400 or higher** — DRF's own exceptions,
Django's URL-resolution 404s, 405s, and uncaught 500s alike — has exactly
this shape:

```json
{
  "code": "price_changed",
  "message": "The price of one or more items in your cart has changed.",
  "details": [
    {"product_id": 7, "old_price": 1200.0, "new_price": 1350.0}
  ],
  "request_id": "8f14e45fea1f5c1c9a5b0c9e2f6d7a81"
}
```

| Field | Meaning |
|---|---|
| `code` | Stable, `snake_case`, never translated. **Branch on this.** |
| `message` | One human sentence. Localised via `Accept-Language`; **never parse it**. |
| `details` | `null`, a field→messages map, or the structured payload a specific error carries. |
| `request_id` | Same value as the `X-Request-ID` response header. Pass it to support; it matches the traceback line in the server log. |

Success bodies (2xx) are **not** enveloped — they are whatever the endpoint
has always returned.

### Client handling

1. `switch (body.code)` for the cases you care about (`price_changed`,
   `idempotency_key_conflict`, `throttled`, …).
2. Otherwise show `body.message`; for `validation_error` pick
   `body.details[field][0]` for the field you are on.
3. On 429, `Retry-After` (seconds) and `details.wait` both say when to try
   again; on 401, re-authenticate; on 500, show the `request_id`.

---

## 2. Codes emitted by the contract itself

These come from `core/exceptions.py`, `core/middleware.py` and
`core/idempotency.py`, and apply to **any** endpoint.

| Code | HTTP | Meaning |
|---|---|---|
| `validation_error` | 400 | The payload failed serializer validation. `details` is `{field: [messages]}`. |
| `bad_request` | 400 | Generic 400 with nothing more specific to say. |
| `invalid_idempotency_key` | 400 | The `Idempotency-Key` header is not 1–64 chars of `[A-Za-z0-9-._]`. |
| `not_authenticated` | 401 | No (or expired) credentials on a logged-in endpoint. |
| `authentication_failed` | 401 | Credentials were supplied but rejected. |
| `payment_required` | 402 | Reserved fallback for a 402. |
| `permission_denied` | 403 | Authenticated, but not allowed to do *this*. |
| `not_found` | 404 | Missing object, unknown `/api/…` path, or a version that does not exist. |
| `method_not_allowed` | 405 | Wrong HTTP verb. |
| `not_acceptable` | 406 | `Accept` cannot be served. |
| `conflict` | 409 | Generic conflict. See `idempotency_key_conflict` for the specific one. |
| `idempotency_key_conflict` | 409 | The same `Idempotency-Key` was reused with a different payload. The first response is replayed when the payload matches. |
| `unsupported_media_type` | 415 | Wrong `Content-Type`. |
| `unprocessable_entity` | 422 | Reserved fallback for a 422. |
| `throttled` | 429 | Rate limited. `details.wait` is the seconds to wait; `Retry-After` header also set. |
| `server_error` | 500 | Unhandled exception. No traceback is exposed — correlate with the log via `request_id`. |
| `bad_gateway` | 502 | Upstream failure surfaced by the app. |
| `service_unavailable` | 503 | Dependency (SMS, payment provider) is down. |
| `gateway_timeout` | 504 | Reserved fallback for a 504. |

DRF also contributes its own codes on the occasions where the framework
raises first (`parse_error`, `http_method_not_allowed`, and the field-level
`required`/`blank`/… codes — those last ones live inside
`details[field]`, never at the top level).

---

## 3. Authentication & identity (`apps/users`)

| Code | HTTP | Meaning |
|---|---|---|
| `missing_credentials` | 400 | Login payload omitted a required field. |
| `invalid_credentials` | 401 | Wrong email/password or phone/OTP; inactive account. Never says *which* half was wrong. |
| `account_disabled` | 403 | The account is disabled. |
| `identity_not_verified` | 403 | Verified-seller gate: identity check not passed. |
| `invalid_verification_link` | 400 | Email-verify link missing its parameters. |
| `invalid_verification_token` | 400 | Verification token invalid or expired. |
| `invalid_reset_token` | 400 | Password-reset token invalid or expired. |
| `old_password_incorrect` | 400 | Change-password: current password wrong. |
| `phone_already_verified` | 400 | Phone re-verification attempt on an already-verified number. Message in `details.phone_number`. |
| `phone_already_registered` | 400 | The phone number belongs to another account. Message in `details.phone_number`. |
| `invalid_otp` | 400 | Wrong or expired one-time code. |
| `sms_delivery_unavailable` | 503 | The SMS provider could not be reached. |

### Social sign-in (`apps/users`)

| Code | HTTP | Meaning |
|---|---|---|
| `social_token_rejected` | 400 | The provider refused the ID token (bad signature, wrong audience, wrong issuer). |
| `social_provider_unavailable` | 502 | The provider's own upstream failed. |
| `social_signin_not_configured` | 503 | No client ID/secret configured for that provider. |
| `social_auth_failed` | 502 | Any other `SocialError`; the status comes from the underlying failure. |

### Permissions (`apps/users/permissions.py`)

| Code | HTTP | Meaning |
|---|---|---|
| `seller_required` | 403 | Not a seller. |
| `not_store_owner` | 403 | Seller, but not the owner of *this* store. |
| `not_listing_owner` | 403 | Seller, but not the author of *this* listing. |

---

## 4. Catalogue (`apps/products`, `apps/stores`, `apps/inventory`)

| Code | HTTP | Meaning |
|---|---|---|
| `product_id_required` | 400 | Wishlist add omitted `product_id`. |
| `product_not_found` | 404 | Unknown product (also on the inventory update path). |
| `not_in_wishlist` | 404 | Product is not in this user's wishlist. |
| `already_reviewed` | 400 | User already reviewed this product. `details.review_id` is the existing one. |
| `store_exists` | 400 | The seller already owns a store. |
| `store_not_found` | 404 | No store for this seller yet (my store, stats, analytics). |
| `insufficient_stock` | 400 | Stock reservation or inventory adjustment would go negative. |
| `seller_required` | 403 | Low-stock endpoint reached by a non-seller. |
| `incomplete_listing` | 400 | `publish` on a draft missing required fields; `details.missing` lists the serializer fields to fix. |
| `invalid_attributes` | 400 | `publish`: the draft's `attributes_json` fails its category's rules; `details.errors` is the per-key map. |
| `quota_reached` | 400 | `publish` would exceed the seller's active-listing tier; `details` carries `{quota, active}`. |
| `possible_duplicate` | 400 | The seller already posted a very similar listing; `details.duplicate_of` is its id. Retry with `allow_duplicate=true` intent on the client after an explicit confirmation. |
| `wrong_listing_type` | 400 | The wizard was asked to create a `STORE_PRODUCT` (store SKUs go through `/products/seller/create/`). |
| `draft_limit` | 400 | Too many saved drafts; `details.limit` is the cap (`MAX_DRAFT_LISTINGS`). |
| `invalid_transition` | 400 | Lifecycle action is not allowed from this listing status (`details.action`, `details.status`). |

### Media uploads (`apps/media`)

| Code | HTTP | Meaning |
|---|---|---|
| `unsupported_image` | 400 | The bytes are not a JPEG/PNG/WebP/GIF. The real format is sniffed from magic bytes — the filename and `Content-Type` are ignored. `details.allowed` lists the formats. |
| `image_too_large` | 413 | The upload exceeds `MEDIA_MAX_UPLOAD_BYTES` (default 10 MB); `details.limit_bytes` says the ceiling. |
| `image_dimensions` | 400 | Width/height outside `MEDIA_MIN_DIMENSION`…`MEDIA_MAX_DIMENSION`, or more pixels than `MEDIA_MAX_PIXELS`. |
| `upload_rejected` | 400 | The configured malware scanner (`MEDIA_SCAN_HOOK`) rejected the file — or could not run, in which case the upload fails closed. |
| `image_in_use` | 409 | Deleting an upload that a listing still references. Remove it from the listing first. |
| `image_not_found` | 404 | `POST /media/images/import/` was given an object key outside `uploads/`, or the object no longer exists. |

---

## 5. Cart, checkout & orders (`apps/orders`)

| Code | HTTP | Meaning |
|---|---|---|
| `empty_cart` | 400 | Checkout with nothing to buy. |
| `product_unavailable` | 400 | A cart line's product was deleted, unpublished, sold/expired/archived, or is a classified (never cartable — Phase 13). |
| `price_changed` | 400 | Cart prices are stale. `details` lists `{product_id, old_price, new_price}`. |
| `address_not_found` | 400 | Shipping address unknown or not the buyer's. |
| `insufficient_stock` | 400 | Reservation lost the race; the affected lines are listed. |
| `payment_failed` | 400 | Gateway declined; nothing committed (stock is returned). |
| `order_error` | 400 | Generic domain failure with nothing more specific to say. |
| `cart_item_not_found` | 404 | Cart line missing, or not the caller's. |
| `order_not_found` | 404 | Order missing, or not this seller's. |
| `invalid_order_status` | 400 | Status value is not one of `Order.STATUS_CHOICES`. |

---

## 6. Payments (`apps/payments`)

| Code | HTTP | Meaning |
|---|---|---|
| `order_id_required` | 400 | Simulated payment payload had no `order_id`. |
| `order_not_found` | 404 | Order missing or not the caller's — deliberately the same answer, so an order id cannot be probed. |
| `already_paid` | 400 | Capture on an order that is already paid (including the loser of a concurrent capture). |
| `order_cancelled` | 400 | Capture on a cancelled / non-payable order. |
| `payment_failed` | 400 | Unexpected capture failure; the traceback is logged, the message stays generic. |
| `not_paid` | 400 | Refund on an order that was never successfully paid (also covers already-refunded). |
| `already_delivered` | 400 | Refund on a delivered order — needs support. |
| `no_successful_transaction` | 400 | Paid, but no successful `Transaction` row to refund against. |
| `refund_failed` | 400 | Unexpected refund failure; traceback logged. |
| `payment_error` | 400 | Base class for the family — rarely seen directly. |

---

## 7. Idempotency

Endpoints that move money or create a listing honour **`Idempotency-Key`**
(header) and, for checkout and simulated payment, the body field of the same
name. The header wins when both are sent.

| Situation | Result |
|---|---|
| First request | Normal response + `Idempotency-Replayed: false` omitted (no header) |
| Replay, same payload | The **original** response, replayed, with `Idempotency-Replayed: true` |
| Replay, different payload | 409 `idempotency_key_conflict` |
| Malformed key | 400 `invalid_idempotency_key` |

Keys are remembered for 24 hours per (user, endpoint, scope).

Covered: `POST /api/v1/orders/checkout/`, `POST /api/v1/payments/simulate/`,
`POST /api/v1/payments/refund/<order_id>/`,
`POST /api/v1/products/seller/create/`.

---

## 8. Versioning

The API is served under **`/api/v1/`** only. `X-API-Version: v1` is set on
every API response. An unversioned path (`/api/products/`) or a version that
does not exist answers with the ordinary 404 envelope (`not_found`), not a
redirect and not an HTML error page.

Adding `v2` means mounting a second URL prefix and adding `"v2"` to
`PathVersioning.allowed_versions` — v1 clients are untouched.

---

## 9. Stability

- **`code` is an API surface.** Renaming one is a breaking change; add a new
  code and keep the old one working for a release instead.
- **`message` is not.** It is localised and may be reworded at any time.
- **Status codes do not change** when a body is re-shaped.
- The envelope's four keys are pinned by `backend/tests/test_api_contract.py`;
  this file's coverage of codes is pinned by
  `backend/tests/test_error_codes_doc.py`.
