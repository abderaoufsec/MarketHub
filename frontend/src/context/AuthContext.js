'use client'

import React, { createContext, useState, useContext, useEffect } from 'react'
import { authAPI } from '../lib/api'
import Cookies from 'js-cookie'
import { useRouter, usePathname } from 'next/navigation'

const AuthContext = createContext()

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
      const token = Cookies.get('access_token')
      if (token) {
        const response = await authAPI.getProfile()
        setUser(response.data)
      }
    } catch (error) {
      console.error('Auth check failed:', error)
      Cookies.remove('access_token')
      Cookies.remove('refresh_token')
    } finally {
      setLoading(false)
    }
  }

  const login = async (email, password) => {
    try {
      const response = await authAPI.login({ email, password })
      const { user: userData, access, refresh } = response.data

      Cookies.set('access_token', access, { expires: 7 })
      Cookies.set('refresh_token', refresh, { expires: 7 })

      setUser(userData)
      return { success: true, user: userData }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.error || 'Login failed',
      }
    }
  }

  const register = async (data) => {
    try {
      const response = await authAPI.register(data)
      return { success: true, data: response.data }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data || 'Registration failed',
      }
    }
  }

  const logout = async () => {
    try {
      const refreshToken = Cookies.get('refresh_token')
      await authAPI.logout(refreshToken)
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      Cookies.remove('access_token')
      Cookies.remove('refresh_token')
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
      return {
        success: false,
        error: error.response?.data || 'Update failed',
      }
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
