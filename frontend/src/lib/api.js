import axios from 'axios'
import Cookies from 'js-cookie'
import { API_URL } from './env'
import { DEFAULT_LOCALE, LOCALE_COOKIE, isLocale } from '../i18n/config'

// Create axios instance
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
})

const SAFE_METHODS = new Set(['get', 'head', 'options', 'trace'])
// Readable session flag set by the backend next to the HttpOnly JWT cookies.
// The tokens themselves are unreadable by design (Phase 7); this only tells
// the client whether a session restore is worth attempting.
const SESSION_HINT = 'mh_session'

/**
 * Make sure the readable double-submit `csrftoken` cookie exists and return
 * it. Unsafe requests must echo it as `X-CSRFToken`: cookie-authenticated
 * writes are CSRF-checked server side (the browser would attach the JWT
 * cookie automatically otherwise).
 */
async function ensureCsrfToken() {
  const existing = Cookies.get('csrftoken')
  if (existing) return existing
  try {
    await axios.get(`${API_URL}/auth/csrf/`, { withCredentials: true })
  } catch {
    // Best effort: anonymous endpoints don't need CSRF anyway. A cookie-
    // authenticated write will fail loudly with 403 if the cookie is missing.
  }
  return Cookies.get('csrftoken')
}

// Request interceptor: attach the CSRF header on unsafe methods. The JWTs
// travel in HttpOnly cookies automatically (withCredentials) — there is no
// token for JavaScript to read or attach.
api.interceptors.request.use(async (config) => {
  // Phase 11: every translated API surface (error envelope, *_label fields,
  // geography names) follows the UI language the same way the frontend does —
  // from the `mh_locale` cookie. LocaleMiddleware on the backend reads this
  // header; without it the API would answer French under an Arabic UI.
  const localeCookie = Cookies.get(LOCALE_COOKIE)
  config.headers['Accept-Language'] = isLocale(localeCookie)
    ? localeCookie
    : DEFAULT_LOCALE

  const method = (config.method || 'get').toLowerCase()
  if (!SAFE_METHODS.has(method)) {
    const token = await ensureCsrfToken()
    if (token) {
      config.headers['X-CSRFToken'] = token
    }
  }
  return config
})

// Response interceptor: on 401, rotate the refresh cookie once and retry.
// Only attempted when the session hint says someone is logged in, so public
// pages for anonymous visitors never trigger a refresh round-trip.
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      Cookies.get(SESSION_HINT)
    ) {
      originalRequest._retry = true

      try {
        const csrf = await ensureCsrfToken()
        await axios.post(
          `${API_URL}/auth/token/refresh/`,
          {},
          {
            withCredentials: true,
            headers: csrf ? { 'X-CSRFToken': csrf } : {},
          }
        )
        // New access cookie is set — replay the original request.
        return api(originalRequest)
      } catch (refreshError) {
        // Session is dead: clear the hint and send the user to login.
        Cookies.remove(SESSION_HINT)
        window.location.href = '/login'
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

export default api

// API Service functions
export const authAPI = {
  register: (data) => api.post('/auth/register/', data),
  login: (data) => api.post('/auth/login/', data),
  // Blacklists the refresh cookie and clears the HttpOnly pair server side.
  logout: () => api.post('/auth/logout/', {}),
  // Phase 8: the backend route is /verify-email/<uidb64>/<token>/ — both
  // parts are path segments (the old single-token call 404'd on every link).
  verifyEmail: (uidb64, token) =>
    api.get(`/auth/verify-email/${uidb64}/${token}/`),
  resendVerification: (data) => api.post('/auth/verify-email/resend/', data),
  // Phase 8: password recovery (email link and SMS-code paths).
  forgotPassword: (data) => api.post('/auth/password/forgot/', data),
  resetPassword: (data) => api.post('/auth/password/reset/', data),
  // Phase 8: phone OTP — request a code, sign in with it, reset with it,
  // or bind the number to the signed-in account.
  requestPhoneOtp: (data) => api.post('/auth/phone/otp/', data),
  loginWithPhone: (data) => api.post('/auth/phone/login/', data),
  resetPasswordWithPhone: (data) => api.post('/auth/phone/reset/', data),
  verifyPhone: (data) => api.post('/auth/phone/verify/', data),
  // Phase 8: Google/Facebook sign-in (tokens verified server-side).
  socialLogin: (data) => api.post('/auth/social/', data),
  getProfile: () => api.get('/auth/profile/'),
  updateProfile: (data) => api.put('/auth/profile/', data),
  changePassword: (data) => api.post('/auth/change-password/', data),
}

export const addressesAPI = {
  list: () => api.get('/auth/addresses/'),
  get: (id) => api.get(`/auth/addresses/${id}/`),
  create: (data) => api.post('/auth/addresses/', data),
  update: (id, data) => api.put(`/auth/addresses/${id}/`, data),
  delete: (id) => api.delete(`/auth/addresses/${id}/`),
}

export const storesAPI = {
  list: (params) => api.get('/stores/', { params }),
  get: (slug) => api.get(`/stores/${slug}/`),
  create: (data) => api.post('/stores/seller/create/', data),
  getMyStore: () => api.get('/stores/seller/my-store/'),
  updateMyStore: (data) => api.put('/stores/seller/my-store/', data),
  getStats: () => api.get('/stores/seller/stats/'),
}

export const productsAPI = {
  list: (params) => api.get('/products/', { params }),
  get: (id) => api.get(`/products/${id}/`),
  getById: (id) => api.get(`/products/seller/${id}/`), // For seller to get their own product
  create: (data) => api.post('/products/seller/create/', data),
  update: (id, data) => api.put(`/products/seller/${id}/`, data),
  delete: (id) => api.delete(`/products/seller/${id}/`),
  featured: () => api.get('/products/featured/'),
  sellerList: () => api.get('/products/seller/list/'),
  search: (params) => api.get('/products/search/', { params }),
}

export const ordersAPI = {
  list: () => api.get('/orders/'),
  get: (id) => api.get(`/orders/${id}/`),
  checkout: (data) => api.post('/orders/checkout/', data),
  sellerList: () => api.get('/orders/seller/list/'),
  updateStatus: (orderId, data) =>
    api.put(`/orders/seller/${orderId}/update-status/`, data),
}

export const cartAPI = {
  get: () => api.get('/orders/cart/'),
  add: (data) => api.post('/orders/cart/add/', data),
  update: (itemId, data) => api.put(`/orders/cart/items/${itemId}/`, data),
  remove: (itemId) => api.delete(`/orders/cart/items/${itemId}/remove/`),
  clear: () => api.delete('/orders/cart/clear/'),
  // Accept the current catalogue prices after checkout reports "price_changed".
  refreshPrices: () => api.post('/orders/cart/refresh-prices/', {}),
}

// ==================== REVIEWS API ====================
export const reviewsAPI = {
  // Get all reviews for a product
  listByProduct: (productId) => api.get(`/products/${productId}/reviews/`),

  // Create a review
  create: (data) => api.post('/products/reviews/create/', data),

  // Get user's own reviews
  myReviews: () => api.get('/products/reviews/my-reviews/'),

  // Get, update or delete a specific review
  get: (reviewId) => api.get(`/products/reviews/${reviewId}/`),
  update: (reviewId, data) => api.put(`/products/reviews/${reviewId}/`, data),
  delete: (reviewId) => api.delete(`/products/reviews/${reviewId}/`),

  // Check if user has reviewed a product
  checkUserReview: (productId) =>
    api.get(`/products/${productId}/check-review/`),
}

// ==================== WISHLIST API ====================
export const wishlistAPI = {
  // Get all wishlist items
  list: () => api.get('/products/wishlist/'),

  // Add product to wishlist
  add: (productId) =>
    api.post('/products/wishlist/add/', { product_id: productId }),

  // Remove product from wishlist
  remove: (productId) => api.delete(`/products/wishlist/remove/${productId}/`),

  // Check if product is in wishlist
  check: (productId) => api.get(`/products/wishlist/check/${productId}/`),

  // Clear entire wishlist
  clear: () => api.delete('/products/wishlist/clear/'),
}

// ==================== PAYMENTS API ====================
export const paymentsAPI = {
  // List user's transactions
  transactions: () => api.get('/payments/transactions/'),

  // Simulate payment for an order
  simulatePayment: (data) => api.post('/payments/simulate/', data),

  // Process refund
  refund: (orderId) => api.post(`/payments/refund/${orderId}/`),

  // Get payment status
  getStatus: (orderId) => api.get(`/payments/status/${orderId}/`),

  // Seller commissions
  sellerCommissions: () => api.get('/payments/seller/commissions/'),
}
