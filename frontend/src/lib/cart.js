/**
 * Pure cart math, extracted from the cart page so it can be unit-tested and
 * reused (checkout summary, order review) without duplicating the formulas.
 *
 * All amounts arrive from the API as decimal strings ("19900.00"); the code
 * works in floats for display. How they are *rendered* is no longer decided
 * here: money formatting moved to `src/lib/currency.js` (DZD, locale-aware,
 * standard/millions modes — Phase 11), and components read it through the
 * `usePrice()` hook.
 */

/** Line total for one cart item: unit price × quantity. */
export function lineTotal(item) {
  const price = parseFloat(item?.price_at_time_of_addition)
  const quantity = Number(item?.quantity) || 0
  if (Number.isNaN(price)) return 0
  return price * quantity
}

/** Sum of every line total; 0 for a missing/empty cart. */
export function cartSubtotal(items) {
  if (!Array.isArray(items)) return 0
  return items.reduce((sum, item) => sum + lineTotal(item), 0)
}

/** Total number of units across all lines (the header cart badge count). */
export function cartItemCount(items) {
  if (!Array.isArray(items)) return 0
  return items.reduce((sum, item) => sum + (Number(item?.quantity) || 0), 0)
}
