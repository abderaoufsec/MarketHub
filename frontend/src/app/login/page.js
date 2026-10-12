'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '../../context/AuthContext'
import { authAPI } from '../../lib/api'
import { Mail, Lock, Phone, KeyRound, AlertCircle } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'
import LoadingSpinner from '../../components/common/LoadingSpinner'

export default function LoginPage() {
  const router = useRouter()
  const { login } = useAuth()
  // 'password' — the classic pair (the identifier accepts an email *or* a
  // verified phone number, Phase 8); 'otp' — passwordless SMS code login.
  const [mode, setMode] = useState('password')
  const [formData, setFormData] = useState({
    email: '',
    password: '',
  })
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [otpLoading, setOtpLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const result = await login(formData.email, formData.password)

      if (result.success) {
        toast.success(
          `Welcome back, ${
            result.user.first_name || result.user.username || 'friend'
          }!`
        )
        // Redirect based on user type
        setTimeout(() => {
          if (result.user.is_seller) {
            router.push('/seller/dashboard')
          } else {
            router.push('/products')
          }
        }, 500)
      } else {
        setError(result.error)
        toast.error(result.error || 'Login failed')
      }
    } catch (err) {
      const errorMessage = 'An unexpected error occurred'
      setError(errorMessage)
      toast.error(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  const sendCode = async (e) => {
    e.preventDefault()
    setError('')
    setOtpLoading(true)
    try {
      await authAPI.requestPhoneOtp({
        phone_number: phone,
        purpose: 'login',
      })
      setCodeSent(true)
      toast.success('Code sent. It expires in 5 minutes.')
    } catch (err) {
      const data = err.response?.data
      const detail =
        data?.phone_number?.[0] || data?.detail || 'Could not send the code.'
      setError(detail)
      toast.error(detail)
    } finally {
      setOtpLoading(false)
    }
  }

  const loginWithCode = async (e) => {
    e.preventDefault()
    setError('')
    setOtpLoading(true)
    try {
      const response = await authAPI.loginWithPhone({
        phone_number: phone,
        code,
      })
      toast.success(
        `Welcome back, ${
          response.data.user.first_name ||
          response.data.user.username ||
          'friend'
        }!`
      )
      setTimeout(() => {
        if (response.data.user.is_seller) {
          router.push('/seller/dashboard')
        } else {
          router.push('/products')
        }
      }, 500)
    } catch (err) {
      const data = err.response?.data
      const detail =
        data?.error || 'That code is invalid or has expired. Try again.'
      setError(detail)
      toast.error(detail)
    } finally {
      setOtpLoading(false)
    }
  }

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    })
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 py-12 px-4 sm:px-6 lg:px-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="max-w-md w-full space-y-8"
      >
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <h2 className="mt-6 text-center text-4xl font-bold gradient-text">
            Sign in to your account
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Or{' '}
            <Link
              href="/register"
              className="font-medium text-primary hover:text-secondary transition-colors"
            >
              create a new account
            </Link>
          </p>
        </motion.div>

        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center shadow-sm"
            >
              <AlertCircle className="h-5 w-5 mr-2 flex-shrink-0" />
              <span>{error}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Sign-in method */}
        <div className="grid grid-cols-2 gap-2 bg-white p-1 rounded-xl border border-gray-200 shadow-sm">
          <button
            type="button"
            onClick={() => {
              setMode('password')
              setError('')
            }}
            className={`flex items-center justify-center gap-2 py-2 px-3 text-sm font-medium rounded-lg transition-colors ${
              mode === 'password'
                ? 'bg-primary text-white shadow'
                : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <Lock className="h-4 w-4" />
            Password
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('otp')
              setError('')
            }}
            className={`flex items-center justify-center gap-2 py-2 px-3 text-sm font-medium rounded-lg transition-colors ${
              mode === 'otp'
                ? 'bg-primary text-white shadow'
                : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <Phone className="h-4 w-4" />
            SMS code
          </button>
        </div>

        <AnimatePresence mode="wait">
          {mode === 'password' ? (
            <motion.form
              key="password"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ delay: 0.1 }}
              className="space-y-6 bg-white p-8 rounded-xl shadow-lg border border-gray-100"
              onSubmit={handleSubmit}
            >
              <div className="space-y-4">
                <motion.div
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.2 }}
                >
                  <label
                    htmlFor="email"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Email or phone number
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <Mail className="h-5 w-5 text-gray-400" />
                    </div>
                    <input
                      id="email"
                      name="email"
                      type="text"
                      autoComplete="username"
                      required
                      value={formData.email}
                      onChange={handleChange}
                      className="input-field pl-10"
                      placeholder="Email address"
                    />
                  </div>
                  <p className="mt-1 text-xs text-gray-500">
                    Phone sign-in works with a verified Algerian number (+213…).
                  </p>
                </motion.div>

                <motion.div
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 }}
                >
                  <label
                    htmlFor="password"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Password
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <Lock className="h-5 w-5 text-gray-400" />
                    </div>
                    <input
                      id="password"
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      required
                      value={formData.password}
                      onChange={handleChange}
                      className="input-field pl-10"
                      placeholder="Password"
                    />
                  </div>
                </motion.div>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <input
                    id="remember-me"
                    name="remember-me"
                    type="checkbox"
                    className="h-4 w-4 text-primary focus:ring-primary border-gray-300 rounded"
                  />
                  <label
                    htmlFor="remember-me"
                    className="ml-2 block text-sm text-gray-900"
                  >
                    Remember me
                  </label>
                </div>

                <div className="text-sm">
                  <Link
                    href="/forgot-password"
                    className="font-medium text-primary hover:text-secondary"
                  >
                    Forgot your password?
                  </Link>
                </div>
              </div>

              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
              >
                <motion.button
                  type="submit"
                  disabled={loading}
                  whileHover={{ scale: loading ? 1 : 1.02 }}
                  whileTap={{ scale: loading ? 1 : 0.98 }}
                  className="group relative w-full flex justify-center items-center gap-2 py-3 px-4 border border-transparent text-sm font-medium rounded-lg text-white bg-primary hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg transition-all"
                >
                  {loading ? (
                    <>
                      <LoadingSpinner size="sm" />
                      Signing in...
                    </>
                  ) : (
                    'Sign in'
                  )}
                </motion.button>
              </motion.div>
            </motion.form>
          ) : (
            <motion.form
              key="otp"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ delay: 0.1 }}
              className="space-y-6 bg-white p-8 rounded-xl shadow-lg border border-gray-100"
              onSubmit={codeSent ? loginWithCode : sendCode}
            >
              <div className="space-y-4">
                <div>
                  <label
                    htmlFor="phone_number"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Phone number
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <Phone className="h-5 w-5 text-gray-400" />
                    </div>
                    <input
                      id="phone_number"
                      name="phone_number"
                      type="tel"
                      autoComplete="tel"
                      required
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      className="input-field pl-10"
                      placeholder="0555 12 34 56"
                      disabled={codeSent}
                    />
                  </div>
                </div>

                <AnimatePresence>
                  {codeSent && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                    >
                      <label
                        htmlFor="otp_code"
                        className="block text-sm font-medium text-gray-700 mb-1"
                      >
                        Verification code
                      </label>
                      <input
                        id="otp_code"
                        name="otp_code"
                        type="text"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        maxLength={6}
                        required
                        value={code}
                        onChange={(e) =>
                          setCode(e.target.value.replace(/\D/g, ''))
                        }
                        className="input-field w-full text-center tracking-[0.5em]"
                        placeholder="000000"
                      />
                      <p className="mt-1 text-xs text-gray-500">
                        Sent to {phone}.{' '}
                        <button
                          type="button"
                          onClick={() => setCodeSent(false)}
                          className="text-primary hover:text-secondary"
                        >
                          Change number
                        </button>
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <motion.button
                type="submit"
                disabled={otpLoading}
                whileHover={{ scale: otpLoading ? 1 : 1.02 }}
                whileTap={{ scale: otpLoading ? 1 : 0.98 }}
                className="w-full flex justify-center items-center gap-2 py-3 px-4 border border-transparent text-sm font-medium rounded-lg text-white bg-primary hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg transition-all"
              >
                {otpLoading ? (
                  <>
                    <LoadingSpinner size="sm" />
                    Working...
                  </>
                ) : codeSent ? (
                  <>
                    <KeyRound className="h-4 w-4" />
                    Sign in with code
                  </>
                ) : (
                  <>
                    <Phone className="h-4 w-4" />
                    Send SMS code
                  </>
                )}
              </motion.button>

              <p className="text-xs text-center text-gray-500">
                No password needed — the code signs you in.
              </p>
            </motion.form>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  )
}
