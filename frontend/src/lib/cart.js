/**
 * Pure cart math, extracted from the cart page so it can be unit-tested and
 * reused (checkout summary, order review) without duplicating the formulas.
 *
 * All amounts arrive from the API as decimal strings ("19900.00"); the code
 * works in floats for display, and `formatPrice` is the single place that
 * decides how they are rendered.
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

/** Render a numeric amount as a display price, e.g. 19900 -> "$19900.00". */
export function formatPrice(amount) {
  const value = parseFloat(amount)
  return `$${(Number.isNaN(value) ? 0 : value).toFixed(2)}`
}
