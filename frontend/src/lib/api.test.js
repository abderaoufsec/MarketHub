/**
 * Axios client interceptors (Phase 7 — HttpOnly cookie session):
 *  - unsafe methods must echo the readable `csrftoken` cookie as `X-CSRFToken`
 *  - no `Authorization` header ever: the JWTs live in HttpOnly cookies
 *  - on 401 with a session hint, the cookie refresh runs once and retries —
 *    or the user is sent to /login when the refresh itself fails.
 */
import axios from 'axios'
import AxiosMockAdapter from 'axios-mock-adapter'
import Cookies from 'js-cookie'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import api, { authAPI, cartAPI, productsAPI } from './api'

// The base URL (…/api/v1 since Phase 9) comes from NEXT_PUBLIC_API_URL; these
// absolute URLs are the two calls that go around the shared axios instance.
const REFRESH_URL = 'http://api.test/api/v1/auth/token/refresh/'
const CSRF_URL = 'http://api.test/api/v1/auth/csrf/'

let apiMock // mocks the shared `api` instance (app requests)
let axiosMock // mocks bare axios (the csrf bootstrap + refresh calls)

beforeEach(() => {
  // `axios-mock-adapter` restores the adapter on restore(), so each test gets
  // a clean slate without leaking handlers into the next one.
  apiMock = new AxiosMockAdapter(api)
  axiosMock = new AxiosMockAdapter(axios)
})

afterEach(() => {
  apiMock.restore()
  axiosMock.restore()
  vi.restoreAllMocks()
})

describe('request interceptor — CSRF, never Authorization', () => {
  it('sends no Authorization header (tokens are HttpOnly)', async () => {
    Cookies.set('mh_session', '1')
    apiMock.onGet('/orders/').reply(200, [])

    await api.get('/orders/')

    expect(apiMock.history.get[0].headers.Authorization).toBeUndefined()
  })

  it('attaches X-CSRFToken on unsafe methods when the cookie exists', async () => {
    Cookies.set('csrftoken', 'csrf-abc')
    apiMock.onPost('/orders/checkout/').reply(200, {})

    await api.post('/orders/checkout/', { items: [] })

    expect(apiMock.history.post[0].headers['X-CSRFToken']).toBe('csrf-abc')
    expect(apiMock.history.post[0].headers.Authorization).toBeUndefined()
    // cookie present -> no bootstrap round-trip
    expect(axiosMock.history.get).toHaveLength(0)
  })

  it('bootstraps the CSRF cookie first when it is missing', async () => {
    axiosMock.onGet(CSRF_URL).reply(() => {
      // The real endpoint answers with a Set-Cookie header; jsdom does not
      // process it, so simulate the browser storing it.
      Cookies.set('csrftoken', 'from-server')
      return [200, { detail: 'CSRF cookie set' }]
    })
    apiMock.onPost('/orders/cart/add/').reply(201, {})

    await api.post('/orders/cart/add/', { product_id: 1 })

    expect(axiosMock.history.get[0].url).toBe(CSRF_URL)
    expect(apiMock.history.post[0].headers['X-CSRFToken']).toBe('from-server')
  })

  it('leaves safe GETs alone (no CSRF header, no bootstrap)', async () => {
    Cookies.set('csrftoken', 'csrf-abc')
    apiMock.onGet('/orders/').reply(200, [])

    await api.get('/orders/')

    expect(apiMock.history.get[0].headers['X-CSRFToken']).toBeUndefined()
    expect(axiosMock.history.get).toHaveLength(0)
  })
})

describe('response interceptor — cookie session refresh', () => {
  it('refreshes the cookie session and retries the original request once', async () => {
    Cookies.set('mh_session', '1')
    Cookies.set('csrftoken', 'csrf-abc')

    apiMock.onGet('/orders/').replyOnce(401)
    apiMock.onGet('/orders/').reply(200, [{ id: 1 }])
    axiosMock.onPost(REFRESH_URL).reply(200, { detail: 'Session refreshed' })

    const response = await api.get('/orders/')

    expect(response.status).toBe(200)
    expect(response.data).toEqual([{ id: 1 }])
    // the refresh used the HttpOnly cookie: empty body, credentials included
    expect(axiosMock.history.post[0].url).toBe(REFRESH_URL)
    expect(JSON.parse(axiosMock.history.post[0].data)).toEqual({})
    expect(axiosMock.history.post[0].withCredentials).toBe(true)
    expect(axiosMock.history.post[0].headers['X-CSRFToken']).toBe('csrf-abc')
    // the retry still carries no Authorization header (cookie does the work)
    expect(apiMock.history.get[1].headers.Authorization).toBeUndefined()
  })

  it('gives up after one retry to avoid infinite loops', async () => {
    Cookies.set('mh_session', '1')
    Cookies.set('csrftoken', 'csrf-abc')

    apiMock.onGet('/orders/').reply(401)
    axiosMock.onPost(REFRESH_URL).reply(200, { detail: 'Session refreshed' })

    await expect(api.get('/orders/')).rejects.toMatchObject({
      response: { status: 401 },
    })

    // exactly two attempts: the original + one retry
    expect(apiMock.history.get).toHaveLength(2)
  })

  it('clears the session hint and redirects to /login when refresh fails', async () => {
    Cookies.set('mh_session', '1')
    Cookies.set('csrftoken', 'csrf-abc')

    apiMock.onGet('/orders/').reply(401)
    axiosMock.onPost(REFRESH_URL).reply(401, {
      code: 'token_invalid',
      message: 'Token is invalid.',
      details: null,
      request_id: 'req-1',
    })

    // jsdom does not implement real navigation; stub the redirect target.
    const locationMock = { href: 'http://localhost/' }
    vi.stubGlobal('location', locationMock)

    await expect(api.get('/orders/')).rejects.toBeTruthy()

    expect(Cookies.get('mh_session')).toBeUndefined()
    expect(locationMock.href).toBe('/login')

    vi.unstubAllGlobals()
  })

  it('passes non-401 errors through untouched', async () => {
    // Phase 9 failure envelope: the interceptor ignores the body entirely
    // and the caller (or lib/errors.js) is the one that interprets it.
    apiMock.onGet('/orders/').reply(500, {
      code: 'server_error',
      message: 'boom',
      details: null,
      request_id: 'req-2',
    })

    await expect(api.get('/orders/')).rejects.toMatchObject({
      response: { status: 500 },
    })

    // no refresh attempted for a server error
    expect(axiosMock.history.post).toHaveLength(0)
    expect(apiMock.history.get).toHaveLength(1)
  })

  it('does not attempt a refresh without the session hint', async () => {
    // anonymous visitor: no `mh_session` flag
    apiMock.onGet('/orders/').reply(401)

    await expect(api.get('/orders/')).rejects.toMatchObject({
      response: { status: 401 },
    })
    expect(axiosMock.history.post).toHaveLength(0)
  })
})

describe('service endpoints', () => {
  it('authAPI.login posts credentials to /auth/login/', async () => {
    apiMock.onPost('/auth/login/').reply(200, { user: { id: 1 } })

    await authAPI.login({ email: 'x@y.z', password: 'pw' })

    expect(apiMock.history.post[0].url).toBe('/auth/login/')
    expect(JSON.parse(apiMock.history.post[0].data)).toEqual({
      email: 'x@y.z',
      password: 'pw',
    })
  })

  it('authAPI.logout posts an empty body (server reads the cookie)', async () => {
    Cookies.set('csrftoken', 'csrf-abc')
    apiMock.onPost('/auth/logout/').reply(200, { message: 'Logout successful' })

    await authAPI.logout()

    expect(apiMock.history.post[0].url).toBe('/auth/logout/')
    expect(JSON.parse(apiMock.history.post[0].data)).toEqual({})
    expect(apiMock.history.post[0].headers['X-CSRFToken']).toBe('csrf-abc')
  })

  it('authAPI.verifyEmail puts uidb64 and token in the path (Phase 8)', async () => {
    // The pre-Phase-8 call passed both as query params and 404'd on every
    // emailed link; the backend route is /verify-email/<uidb64>/<token>/.
    apiMock.onGet('/auth/verify-email/bXktdXNlcg/abc123/').reply(200, {
      detail: 'Email verified.',
    })

    const response = await authAPI.verifyEmail('bXktdXNlcg', 'abc123')

    expect(apiMock.history.get[0].url).toBe(
      '/auth/verify-email/bXktdXNlcg/abc123/'
    )
    expect(response.data.detail).toBe('Email verified.')
  })

  it('authAPI password-recovery calls target the Phase 8 routes', async () => {
    apiMock.onPost('/auth/password/forgot/').reply(200, { detail: '…' })
    apiMock.onPost('/auth/password/reset/').reply(200, { detail: '…' })

    await authAPI.forgotPassword({ email: 'x@y.z' })
    await authAPI.resetPassword({ uidb64: 'u', token: 't', new_password: 'p' })

    expect(apiMock.history.post[0].url).toBe('/auth/password/forgot/')
    expect(apiMock.history.post[1].url).toBe('/auth/password/reset/')
  })

  it('authAPI phone endpoints each post to their own route (Phase 8)', async () => {
    apiMock.onPost('/auth/phone/otp/').reply(200, { detail: '…' })
    apiMock.onPost('/auth/phone/login/').reply(200, { access: 'a' })
    apiMock.onPost('/auth/phone/reset/').reply(200, { detail: '…' })
    apiMock.onPost('/auth/phone/verify/').reply(200, { detail: '…' })
    apiMock.onPost('/auth/social/').reply(200, { access: 'a' })

    await authAPI.requestPhoneOtp({ phone_number: '+213555000000' })
    await authAPI.loginWithPhone({
      phone_number: '+213555000000',
      code: '123456',
    })
    await authAPI.resetPasswordWithPhone({
      phone_number: '+213555000000',
      code: '123456',
      new_password: 'pw',
      new_password_confirm: 'pw',
    })
    await authAPI.verifyPhone({
      phone_number: '+213555000000',
      code: '123456',
    })
    await authAPI.socialLogin({ provider: 'google', access_token: 'tok' })

    expect(apiMock.history.post.map((r) => r.url)).toEqual([
      '/auth/phone/otp/',
      '/auth/phone/login/',
      '/auth/phone/reset/',
      '/auth/phone/verify/',
      '/auth/social/',
    ])
  })

  it('cartAPI.update PUTs the new quantity to the item URL', async () => {
    Cookies.set('csrftoken', 'csrf-abc')
    apiMock.onPut('/orders/cart/items/7/').reply(200, { quantity: 3 })

    await cartAPI.update(7, { quantity: 3 })

    expect(apiMock.history.put[0].url).toBe('/orders/cart/items/7/')
    expect(JSON.parse(apiMock.history.put[0].data)).toEqual({ quantity: 3 })
    expect(apiMock.history.put[0].headers['X-CSRFToken']).toBe('csrf-abc')
  })

  it('productsAPI Phase 13 endpoints target the listing routes', async () => {
    Cookies.set('csrftoken', 'csrf-abc')
    apiMock.onPost('/products/create/').reply(201, { id: 55 })
    apiMock.onPost('/products/55/lifecycle/').reply(200, { id: 55 })
    apiMock.onGet('/products/seller/quota/').reply(200, { listing_quota: 10 })
    apiMock.onGet('/products/55/similar/').reply(200, [])
    apiMock.onGet('/products/55/more-from-seller/').reply(200, [])
    apiMock.onPatch('/products/seller/55/').reply(200, { id: 55 })
    apiMock.onGet('/products/seller/list/').reply(200, { results: [] })

    await productsAPI.createListing({ name: 'Vélo' })
    await productsAPI.lifecycle(55, 'publish', { allow_duplicate: true })
    await productsAPI.quota()
    await productsAPI.similar(55)
    await productsAPI.moreFromSeller(55)
    await productsAPI.updateListing(55, { name: 'Vélo' })
    await productsAPI.sellerList({ status: 'DRAFT' })

    // The wizard's save is POST-once, then PATCH (a PUT would demand every
    // required field the seller has not filled yet).
    expect(apiMock.history.post.map((r) => r.url)).toEqual([
      '/products/create/',
      '/products/55/lifecycle/',
    ])
    expect(JSON.parse(apiMock.history.post[1].data)).toEqual({
      action: 'publish',
      allow_duplicate: true,
    })
    expect(apiMock.history.patch[0].url).toBe('/products/seller/55/')

    // The dashboard tabs are a server-side status filter, not a client slice.
    expect(apiMock.history.get.map((r) => r.url)).toEqual([
      '/products/seller/quota/',
      '/products/55/similar/',
      '/products/55/more-from-seller/',
      '/products/seller/list/',
    ])
    expect(apiMock.history.get[3].params).toEqual({ status: 'DRAFT' })
  })
})
