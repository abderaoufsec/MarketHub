'use client'

import React, { createContext, useState, useContext, useEffect } from 'react'
import { authAPI } from '../lib/api'
import { apiErrorMessage, parseApiError } from '../lib/errors'
import Cookies from 'js-cookie'
import { useRouter, usePathname } from 'next/navigation'

const AuthContext = createContext()

/**
 * Every failure leaves the context as the Phase 9 envelope
 * (`{status, code, message, details, requestId}`) instead of the raw body, so
 * callers branch on `code` and display `message`. The call-site `fallback`
 * seeds that message when the server — or the network — said nothing usable.
 */
const failure = (error, fallback) => ({
  success: false,
  error: { ...parseApiError(error), message: apiErrorMessage(error, fallback) },
})

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    checkAuth()
  }, [])

  const checkAuth = async () => {
    try {
      // The JWTs are HttpOnly; only the readable session hint tells us a
      // session may exist. The interceptor refreshes it transparently.
      const hasSession = Cookies.get('mh_session')
      if (hasSession) {
        const response = await authAPI.getProfile()
        setUser(response.data)
      }
    } catch (error) {
      console.error('Auth check failed:', error)
      Cookies.remove('mh_session')
    } finally {
      setLoading(false)
    }
  }

  const login = async (email, password) => {
    try {
      const response = await authAPI.login({ email, password })
      const { user: userData } = response.data

      // Tokens are set as HttpOnly cookies by the server; nothing to store
      // client side (the `mh_session` hint comes with the same response).
      setUser(userData)
      return { success: true, user: userData }
    } catch (error) {
      return failure(error, 'Login failed')
    }
  }

  const register = async (data) => {
    try {
      const response = await authAPI.register(data)
      return { success: true, data: response.data }
    } catch (error) {
      return failure(error, 'Registration failed')
    }
  }

  const logout = async () => {
    try {
      await authAPI.logout()
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      // Server clears the HttpOnly pair; the readable hint goes here so the
      // UI never attempts a session restore for a logged-out visitor.
      Cookies.remove('mh_session')
      setUser(null)
      router.push('/')
    }
  }

  const updateProfile = async (data) => {
    try {
      const response = await authAPI.updateProfile(data)
      const userData = response.data.user || response.data
      setUser(userData)
      return { success: true, user: userData }
    } catch (error) {
      return failure(error, 'Update failed')
    }
  }

  const value = {
    user,
    loading,
    login,
    register,
    logout,
    updateProfile,
    isAuthenticated: !!user,
    isSeller: user?.is_seller || false,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
