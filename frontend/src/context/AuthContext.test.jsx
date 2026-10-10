import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import Cookies from 'js-cookie'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Mock the API layer before importing the context (ESM imports are hoisted).
vi.mock('../lib/api', () => ({
  authAPI: {
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    getProfile: vi.fn(),
    updateProfile: vi.fn(),
  },
}))

const mockPush = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/',
}))

import { authAPI } from '../lib/api'
import { AuthProvider, useAuth } from './AuthContext'
/** Probe component that exposes the context value to assertions. */
let latestAuth
function AuthProbe() {
  latestAuth = useAuth()
  return (
    <div>
      <span data-testid="user">{latestAuth.user?.email ?? 'anonymous'}</span>
      <span data-testid="loading">{String(latestAuth.loading)}</span>
      <span data-testid="is-seller">{String(latestAuth.isSeller)}</span>
    </div>
  )
}

function renderAuth() {
  return render(
    <AuthProvider>
      <AuthProbe />
    </AuthProvider>
  )
}

const USER = { id: 1, email: 'buyer@example.com', is_seller: false }

beforeEach(() => {
  vi.clearAllMocks()
  Cookies.remove('access_token')
  Cookies.remove('refresh_token')
})

afterEach(() => {
  Cookies.remove('access_token')
  Cookies.remove('refresh_token')
})

describe('useAuth', () => {
  it('throws when used outside the provider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<AuthProbe />)).toThrow(
      'useAuth must be used within an AuthProvider'
    )
    spy.mockRestore()
  })
})

describe('AuthProvider session restore', () => {
  it('stays anonymous and finishes loading when no token cookie exists', async () => {
    renderAuth()

    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    )
    expect(screen.getByTestId('user')).toHaveTextContent('anonymous')
    expect(authAPI.getProfile).not.toHaveBeenCalled()
  })

  it('fetches the profile when an access token cookie exists', async () => {
    Cookies.set('access_token', 'token-123')
    authAPI.getProfile.mockResolvedValue({ data: USER })

    renderAuth()

    await waitFor(() =>
      expect(screen.getByTestId('user')).toHaveTextContent('buyer@example.com')
    )
    expect(authAPI.getProfile).toHaveBeenCalledTimes(1)
    expect(latestAuth.isAuthenticated).toBe(true)
  })

  it('drops stale tokens when the profile fetch fails', async () => {
    Cookies.set('access_token', 'stale')
    Cookies.set('refresh_token', 'stale')
    authAPI.getProfile.mockRejectedValue(new Error('401'))

    renderAuth()

    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    )
    expect(screen.getByTestId('user')).toHaveTextContent('anonymous')
    expect(Cookies.get('access_token')).toBeUndefined()
    expect(Cookies.get('refresh_token')).toBeUndefined()
  })
})

describe('login', () => {
  it('stores tokens and sets the user on success', async () => {
    authAPI.login.mockResolvedValue({
      data: { user: USER, access: 'acc', refresh: 'ref' },
    })
    renderAuth()
    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    )

    const result = await latestAuth.login('buyer@example.com', 'pw')

    expect(result.success).toBe(true)
    expect(result.user).toEqual(USER)
    expect(authAPI.login).toHaveBeenCalledWith({
      email: 'buyer@example.com',
      password: 'pw',
    })
    expect(Cookies.get('access_token')).toBe('acc')
    expect(Cookies.get('refresh_token')).toBe('ref')
    await waitFor(() =>
      expect(screen.getByTestId('user')).toHaveTextContent('buyer@example.com')
    )
  })

  it('returns the backend error message on failure', async () => {
    authAPI.login.mockRejectedValue({
      response: { data: { error: 'Invalid credentials' } },
    })
    renderAuth()
    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    )

    const result = await latestAuth.login('buyer@example.com', 'wrong')

    expect(result).toEqual({ success: false, error: 'Invalid credentials' })
    expect(screen.getByTestId('user')).toHaveTextContent('anonymous')
  })

  it('falls back to a generic message when the error has no body', async () => {
    authAPI.login.mockRejectedValue(new Error('network down'))
    renderAuth()
    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    )

    const result = await latestAuth.login('buyer@example.com', 'pw')

    expect(result.success).toBe(false)
    expect(result.error).toBe('Login failed')
  })
})

describe('logout', () => {
  it('clears cookies, resets the user and navigates home', async () => {
    Cookies.set('access_token', 'acc')
    Cookies.set('refresh_token', 'ref')
    authAPI.getProfile.mockResolvedValue({ data: USER })
    authAPI.logout.mockResolvedValue({})
    renderAuth()
    await waitFor(() =>
      expect(screen.getByTestId('user')).toHaveTextContent('buyer@example.com')
    )

    await latestAuth.logout()

    expect(authAPI.logout).toHaveBeenCalledWith('ref')
    expect(Cookies.get('access_token')).toBeUndefined()
    expect(Cookies.get('refresh_token')).toBeUndefined()
    expect(mockPush).toHaveBeenCalledWith('/')
    await waitFor(() =>
      expect(screen.getByTestId('user')).toHaveTextContent('anonymous')
    )
  })

  it('still clears local state when the API call fails', async () => {
    Cookies.set('access_token', 'acc')
    Cookies.set('refresh_token', 'ref')
    authAPI.getProfile.mockResolvedValue({ data: USER })
    authAPI.logout.mockRejectedValue(new Error('offline'))
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    renderAuth()
    await waitFor(() =>
      expect(screen.getByTestId('user')).toHaveTextContent('buyer@example.com')
    )

    await latestAuth.logout()

    expect(Cookies.get('access_token')).toBeUndefined()
    await waitFor(() =>
      expect(screen.getByTestId('user')).toHaveTextContent('anonymous')
    )
    spy.mockRestore()
  })
})

describe('register', () => {
  it('reports success with the backend payload', async () => {
    authAPI.register.mockResolvedValue({ data: { user: USER } })
    renderAuth()
    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    )

    const result = await latestAuth.register({ email: USER.email })

    expect(result).toEqual({ success: true, data: { user: USER } })
  })

  it('returns field errors from the serializer', async () => {
    const fieldErrors = { email: ['A user with that email already exists.'] }
    authAPI.register.mockRejectedValue({ response: { data: fieldErrors } })
    renderAuth()
    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    )

    const result = await latestAuth.register({ email: USER.email })

    expect(result.success).toBe(false)
    expect(result.error).toEqual(fieldErrors)
  })
})

describe('role flags', () => {
  it('exposes isSeller from the user record', async () => {
    Cookies.set('access_token', 'token-123')
    authAPI.getProfile.mockResolvedValue({
      data: { ...USER, is_seller: true },
    })
    renderAuth()

    await waitFor(() =>
      expect(screen.getByTestId('is-seller')).toHaveTextContent('true')
    )
    expect(latestAuth.isSeller).toBe(true)
  })
})

describe('updateProfile', () => {
  it('replaces the cached user with the updated one', async () => {
    Cookies.set('access_token', 'token-123')
    authAPI.getProfile.mockResolvedValue({ data: USER })
    authAPI.updateProfile.mockResolvedValue({
      data: { user: { ...USER, first_name: 'Nadia' } },
    })
    renderAuth()
    await waitFor(() =>
      expect(screen.getByTestId('user')).toHaveTextContent('buyer@example.com')
    )

    const result = await latestAuth.updateProfile({ first_name: 'Nadia' })

    expect(result.success).toBe(true)
    await waitFor(() => expect(latestAuth.user.first_name).toBe('Nadia'))
  })
})
