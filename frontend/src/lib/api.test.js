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

import api, { authAPI, cartAPI } from './api'

const REFRESH_URL = 'http://api.test/api/auth/token/refresh/'
const CSRF_URL = 'http://api.test/api/auth/csrf/'

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
    axiosMock.onPost(REFRESH_URL).reply(401, { detail: 'Token is invalid' })

    // jsdom does not implement real navigation; stub the redirect target.
    const locationMock = { href: 'http://localhost/' }
    vi.stubGlobal('location', locationMock)

    await expect(api.get('/orders/')).rejects.toBeTruthy()

    expect(Cookies.get('mh_session')).toBeUndefined()
    expect(locationMock.href).toBe('/login')

    vi.unstubAllGlobals()
  })

  it('passes non-401 errors through untouched', async () => {
    apiMock.onGet('/orders/').reply(500, { error: 'boom' })

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

  it('cartAPI.update PUTs the new quantity to the item URL', async () => {
    Cookies.set('csrftoken', 'csrf-abc')
    apiMock.onPut('/orders/cart/items/7/').reply(200, { quantity: 3 })

    await cartAPI.update(7, { quantity: 3 })

    expect(apiMock.history.put[0].url).toBe('/orders/cart/items/7/')
    expect(JSON.parse(apiMock.history.put[0].data)).toEqual({ quantity: 3 })
    expect(apiMock.history.put[0].headers['X-CSRFToken']).toBe('csrf-abc')
  })
})
