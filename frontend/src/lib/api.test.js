/**
 * Axios client interceptors: the request interceptor must attach the JWT, and
 * the response interceptor must transparently refresh an expired token and
 * retry once — or log the user out when the refresh itself fails.
 */
import axios from 'axios'
import AxiosMockAdapter from 'axios-mock-adapter'
import Cookies from 'js-cookie'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import api, { authAPI, cartAPI } from './api'

const REFRESH_URL = 'http://api.test/api/auth/token/refresh/'

let apiMock // mocks the shared `api` instance (app requests)
let axiosMock // mocks bare axios (only used by the refresh call)

beforeEach(() => {
  Cookies.remove('access_token')
  Cookies.remove('refresh_token')
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

describe('request interceptor', () => {
  it('sends no Authorization header when no token cookie exists', async () => {
    apiMock.onGet('/orders/').reply(200, [])

    await api.get('/orders/')

    expect(apiMock.history.get[0].headers.Authorization).toBeUndefined()
  })

  it('attaches the access token as a Bearer header', async () => {
    Cookies.set('access_token', 'token-abc')
    apiMock.onGet('/orders/').reply(200, [])

    await api.get('/orders/')

    expect(apiMock.history.get[0].headers.Authorization).toBe(
      'Bearer token-abc'
    )
  })
})

describe('response interceptor — token refresh', () => {
  it('refreshes an expired token and retries the original request once', async () => {
    Cookies.set('access_token', 'expired-token')
    Cookies.set('refresh_token', 'refresh-xyz')

    apiMock.onGet('/orders/').replyOnce(401)
    apiMock.onGet('/orders/').reply(200, [{ id: 1 }])
    axiosMock.onPost(REFRESH_URL).reply(200, { access: 'fresh-token' })

    const response = await api.get('/orders/')

    expect(response.status).toBe(200)
    expect(response.data).toEqual([{ id: 1 }])
    // the retry carried the refreshed token
    expect(apiMock.history.get[1].headers.Authorization).toBe(
      'Bearer fresh-token'
    )
    // and the new token was persisted for subsequent requests
    expect(Cookies.get('access_token')).toBe('fresh-token')
    expect(axiosMock.history.post[0].data).toContain('refresh-xyz')
  })

  it('gives up after one retry to avoid infinite loops', async () => {
    Cookies.set('access_token', 'expired')
    Cookies.set('refresh_token', 'refresh-xyz')

    apiMock.onGet('/orders/').reply(401)
    axiosMock.onPost(REFRESH_URL).reply(200, { access: 'fresh-token' })

    await expect(api.get('/orders/')).rejects.toMatchObject({
      response: { status: 401 },
    })

    // exactly two attempts: the original + one retry
    expect(apiMock.history.get).toHaveLength(2)
  })

  it('logs the user out and redirects to /login when the refresh fails', async () => {
    Cookies.set('access_token', 'expired')
    Cookies.set('refresh_token', 'dead-refresh')

    apiMock.onGet('/orders/').reply(401)
    axiosMock.onPost(REFRESH_URL).reply(401, { detail: 'Token is invalid' })

    // jsdom does not implement real navigation; stub the redirect target.
    const locationMock = { href: 'http://localhost/' }
    vi.stubGlobal('location', locationMock)

    await expect(api.get('/orders/')).rejects.toBeTruthy()

    expect(Cookies.get('access_token')).toBeUndefined()
    expect(Cookies.get('refresh_token')).toBeUndefined()
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

  it('does not attempt a refresh without a refresh token cookie', async () => {
    Cookies.set('access_token', 'expired')
    // no refresh_token cookie

    apiMock.onGet('/orders/').reply(401)

    await expect(api.get('/orders/')).rejects.toMatchObject({
      response: { status: 401 },
    })
    expect(axiosMock.history.post).toHaveLength(0)
  })
})

describe('service endpoints', () => {
  it('authAPI.login posts credentials to /auth/login/', async () => {
    apiMock.onPost('/auth/login/').reply(200, { access: 'a' })

    await authAPI.login({ email: 'x@y.z', password: 'pw' })

    expect(apiMock.history.post[0].url).toBe('/auth/login/')
    expect(JSON.parse(apiMock.history.post[0].data)).toEqual({
      email: 'x@y.z',
      password: 'pw',
    })
  })

  it('cartAPI.update PUTs the new quantity to the item URL', async () => {
    apiMock.onPut('/orders/cart/items/7/').reply(200, { quantity: 3 })

    await cartAPI.update(7, { quantity: 3 })

    expect(apiMock.history.put[0].url).toBe('/orders/cart/items/7/')
    expect(JSON.parse(apiMock.history.put[0].data)).toEqual({ quantity: 3 })
  })
})
