/**
 * Checkout page — the Phase 6 contract of docs/todo.md:
 *
 * 1. **One authoritative payment path.** Placing the order is a *single*
 *    request; the page must never call a payment endpoint again afterwards
 *    (that double call used to make the buyer see "Payment failed" for an
 *    order that had already been paid). The mocked API module deliberately
 *    exports no `paymentsAPI`, so a regression cannot even be imported.
 * 2. **Prices are re-validated server-side.** A `price_changed` rejection
 *    refreshes the cart, tells the buyer what moved, and does *not* place an
 *    order.
 * 3. **Retries are safe.** The same idempotency key is sent with the request.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CheckoutPage from './page'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    push: vi.fn(),
    checkout: vi.fn(),
    refreshPrices: vi.fn(),
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
  },
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push }),
}))

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}))

vi.mock('../../lib/api', () => ({
  cartAPI: { get: vi.fn(), refreshPrices: mocks.refreshPrices },
  ordersAPI: { checkout: mocks.checkout },
  addressesAPI: { list: vi.fn() },
}))

vi.mock('react-hot-toast', () => ({
  default: { success: mocks.toastSuccess, error: mocks.toastError },
}))

const CART = {
  items: [
    {
      id: 11,
      quantity: 2,
      price_at_time_of_addition: '100.00',
      product: { name: 'E2E Test Phone', images: [] },
    },
  ],
  total_items: 2,
  total_price: '200.00',
}

const ADDRESSES = {
  results: [
    {
      id: 5,
      address_line1: '12 Rue de la Liberté',
      address_line2: '',
      city: 'Blida',
      state_province: 'Blida',
      postal_code: '09000',
      country: 'DZ',
      is_default: true,
    },
  ],
}

async function renderCheckout() {
  const { cartAPI, addressesAPI } = await import('../../lib/api')
  cartAPI.get.mockResolvedValue({ data: CART })
  addressesAPI.list.mockResolvedValue({ data: ADDRESSES })

  render(<CheckoutPage />)

  return screen.findByRole('button', { name: /place order/i })
}

beforeEach(() => {
  vi.clearAllMocks()
})

/** Everything the page is showing, without fighting over which node matches. */
const bodyText = () => document.body.textContent

describe('placing an order', () => {
  it('pays in the checkout request itself and lands on the order page', async () => {
    mocks.checkout.mockResolvedValue({
      data: { orders: [{ id: 42, payment_status: 'SUCCESSFUL' }] },
    })

    const button = await renderCheckout()
    fireEvent.click(button)

    await waitFor(() => expect(mocks.checkout).toHaveBeenCalledTimes(1))
    expect(mocks.checkout).toHaveBeenCalledWith({
      shipping_address_id: 5,
      shipping_method: 'standard',
      // Retrying after a timeout replays this order instead of charging twice.
      idempotency_key: expect.any(String),
    })

    await waitFor(() =>
      expect(mocks.push).toHaveBeenCalledWith('/orders/42?success=true')
    )
    // No second payment request, and no "price changed" recovery.
    expect(mocks.refreshPrices).not.toHaveBeenCalled()
  })

  it('sends a stable idempotency key across retries of the same attempt', async () => {
    mocks.checkout.mockRejectedValueOnce({
      response: {
        status: 502,
        data: {
          code: 'http_502',
          message: 'network down',
          details: null,
          request_id: 'req-1',
        },
      },
    })
    mocks.checkout.mockResolvedValueOnce({
      data: { orders: [{ id: 42, payment_status: 'SUCCESSFUL' }] },
    })

    const button = await renderCheckout()
    fireEvent.click(button)
    await waitFor(() => expect(mocks.toastError).toHaveBeenCalled())
    fireEvent.click(button)
    await waitFor(() => expect(mocks.checkout).toHaveBeenCalledTimes(2))

    const [first, second] = mocks.checkout.mock.calls
    expect(first[0].idempotency_key).toBe(second[0].idempotency_key)
  })
})

describe('when the price changed while checking out', () => {
  // Phase 9 failure envelope: the branch is on `code`, the deltas travel in
  // `details`.
  const rejection = {
    response: {
      status: 409,
      data: {
        code: 'price_changed',
        message: 'The price of one or more items in your cart has changed.',
        details: [
          {
            product_id: 7,
            product_name: 'E2E Test Phone',
            old_price: '100.00',
            new_price: '150.00',
          },
        ],
        request_id: 'req-2',
      },
    },
  }

  it('refreshes the cart and does not place an order', async () => {
    mocks.checkout.mockRejectedValue(rejection)
    mocks.refreshPrices.mockResolvedValue({
      data: {
        updated: rejection.response.data.details,
        cart: {
          ...CART,
          items: [{ ...CART.items[0], price_at_time_of_addition: '150.00' }],
        },
      },
    })

    const button = await renderCheckout()
    fireEvent.click(button)

    await waitFor(() => expect(bodyText()).toContain('Prices have changed'))

    expect(mocks.refreshPrices).toHaveBeenCalledTimes(1)
    expect(mocks.push).not.toHaveBeenCalled()
    // The buyer sees exactly what moved, old price and new price.
    expect(bodyText()).toContain('was $100.00')
    expect(bodyText()).toContain('$150.00')
  })
})

describe('when a line cannot be reserved', () => {
  it('shows the backend message and places nothing', async () => {
    mocks.checkout.mockRejectedValue({
      response: {
        status: 409,
        data: {
          code: 'insufficient_stock',
          message:
            'Insufficient stock for E2E Test Phone. Available: 1, Required: 2',
          details: null,
          request_id: 'req-3',
        },
      },
    })

    const button = await renderCheckout()
    fireEvent.click(button)

    await waitFor(() =>
      expect(bodyText()).toContain(
        'Insufficient stock for E2E Test Phone. Available: 1, Required: 2'
      )
    )
    expect(mocks.push).not.toHaveBeenCalled()
  })
})
