'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { motion, AnimatePresence } from 'framer-motion'
import { Mail, Phone, KeyRound, AlertCircle, CheckCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { authAPI } from '../../lib/api'
import { apiErrorMessage, apiFieldError } from '../../lib/errors'
import LoadingSpinner from '../../components/common/LoadingSpinner'

/**
 * Account recovery (Phase 8 of docs/todo.md).
 *
 * Two routes, because Algeria is phone-first and many accounts have no email:
 *
 * 1. **By email** — asks for the address and mails a reset link; the reply is
 *    identical whether or not the account exists (enumeration defence).
 * 2. **By SMS code** — the only recovery a phone-only account has: request a
 *    code, then set the new password in one step.
 */
export default function ForgotPasswordPage() {
  const router = useRouter()
  const [mode, setMode] = useState('email') // 'email' | 'phone'

  const [email, setEmail] = useState('')
  const [emailSent, setEmailSent] = useState(false)
  const [emailLoading, setEmailLoading] = useState(false)

  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [phoneLoading, setPhoneLoading] = useState(false)
  const [resetLoading, setResetLoading] = useState(false)

  const submitEmail = async (e) => {
    e.preventDefault()
    setEmailLoading(true)
    try {
      await authAPI.forgotPassword({ email })
      setEmailSent(true)
    } catch (error) {
      // 400 only when the address itself is malformed — anything else would
      // leak whether the account exists, so the backend does not do it.
      toast.error(
        apiFieldError(error, 'email') ||
          apiErrorMessage(error, 'Please enter a valid email address.')
      )
    } finally {
      setEmailLoading(false)
    }
  }

  const sendCode = async (e) => {
    e.preventDefault()
    setPhoneLoading(true)
    try {
      await authAPI.requestPhoneOtp({
        phone_number: phone,
        purpose: 'password_reset',
      })
      setCodeSent(true)
      toast.success('If that number has an account, a code is on its way.')
    } catch (error) {
      toast.error(
        apiFieldError(error, 'phone_number') ||
          apiErrorMessage(error, 'Could not send the code.')
      )
    } finally {
      setPhoneLoading(false)
    }
  }

  const resetByPhone = async (e) => {
    e.preventDefault()
    if (newPassword !== passwordConfirm) {
      toast.error('Passwords do not match')
      return
    }
    setResetLoading(true)
    try {
      await authAPI.resetPasswordWithPhone({
        phone_number: phone,
        code,
        new_password: newPassword,
        new_password_confirm: passwordConfirm,
      })
      toast.success('Password reset. You can sign in now.')
      router.push('/login')
    } catch (error) {
      // The specific field message wins over the generic envelope one —
      // "Password must not be the last one" beats "Invalid data.".
      const detail =
        apiFieldError(error, 'new_password') ||
        apiFieldError(error, 'code') ||
        apiFieldError(error, 'phone_number') ||
        apiErrorMessage(error, 'That code is invalid or has expired.')
      toast.error(detail)
    } finally {
      setResetLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 py-12 px-4 sm:px-6 lg:px-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="max-w-md w-full space-y-8"
      >
        <div>
          <h2 className="mt-6 text-center text-4xl font-bold gradient-text">
            Reset your password
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Remembered it?{' '}
            <Link
              href="/login"
              className="font-medium text-primary hover:text-secondary transition-colors"
            >
              Back to sign in
            </Link>
          </p>
        </div>

        {/* Mode toggle */}
        <div className="grid grid-cols-2 gap-2 bg-white p-1 rounded-xl border border-gray-200 shadow-sm">
          <button
            type="button"
            onClick={() => setMode('email')}
            className={`flex items-center justify-center gap-2 py-2 px-3 text-sm font-medium rounded-lg transition-colors ${
              mode === 'email'
                ? 'bg-primary text-white shadow'
                : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <Mail className="h-4 w-4" />
            By email
          </button>
          <button
            type="button"
            onClick={() => setMode('phone')}
            className={`flex items-center justify-center gap-2 py-2 px-3 text-sm font-medium rounded-lg transition-colors ${
              mode === 'phone'
                ? 'bg-primary text-white shadow'
                : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <Phone className="h-4 w-4" />
            By SMS code
          </button>
        </div>

        <AnimatePresence mode="wait">
          {mode === 'email' ? (
            <motion.div
              key="email"
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              className="bg-white p-8 rounded-xl shadow-lg border border-gray-100"
            >
              {emailSent ? (
                <div className="text-center space-y-4">
                  <CheckCircle className="h-14 w-14 text-green-500 mx-auto" />
                  <h3 className="text-lg font-semibold text-gray-900">
                    Check your inbox
                  </h3>
                  <p className="text-sm text-gray-600">
                    If an account exists for{' '}
                    <span className="font-medium">{email}</span>, a reset link
                    is on its way. The link expires in 24 hours.
                  </p>
                  <Link
                    href="/login"
                    className="inline-block py-2 px-4 text-sm font-medium rounded-lg text-primary hover:bg-primary/10 transition-colors"
                  >
                    Back to sign in
                  </Link>
                </div>
              ) : (
                <form onSubmit={submitEmail} className="space-y-4">
                  <div>
                    <label
                      htmlFor="email"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      Email address
                    </label>
                    <input
                      id="email"
                      type="email"
                      required
                      autoComplete="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="input-field w-full"
                      placeholder="you@example.com"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={emailLoading}
                    className="w-full flex items-center justify-center gap-2 py-3 px-4 text-sm font-medium rounded-lg text-white bg-primary hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-md"
                  >
                    {emailLoading ? (
                      <LoadingSpinner size="sm" />
                    ) : (
                      <>
                        <Mail className="h-4 w-4" />
                        Send reset link
                      </>
                    )}
                  </button>
                </form>
              )}
            </motion.div>
          ) : (
            <motion.div
              key="phone"
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              className="bg-white p-8 rounded-xl shadow-lg border border-gray-100"
            >
              <form
                onSubmit={codeSent ? resetByPhone : sendCode}
                className="space-y-4"
              >
                <div>
                  <label
                    htmlFor="phone_number"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Phone number
                  </label>
                  <input
                    id="phone_number"
                    type="tel"
                    required
                    autoComplete="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="input-field w-full"
                    placeholder="0555 12 34 56"
                    disabled={codeSent}
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    The number you registered with, in Algerian format.
                  </p>
                </div>

                <AnimatePresence>
                  {codeSent && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className="space-y-4"
                    >
                      <div className="bg-blue-50 border border-blue-200 text-blue-700 px-3 py-2 rounded-lg text-xs flex items-center gap-2">
                        <AlertCircle className="h-4 w-4 flex-shrink-0" />
                        We sent a 6-digit code to that number. It expires in 5
                        minutes.
                      </div>
                      <div>
                        <label
                          htmlFor="code"
                          className="block text-sm font-medium text-gray-700 mb-1"
                        >
                          Verification code
                        </label>
                        <input
                          id="code"
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
                      </div>
                      <div>
                        <label
                          htmlFor="new_password"
                          className="block text-sm font-medium text-gray-700 mb-1"
                        >
                          New password
                        </label>
                        <input
                          id="new_password"
                          type="password"
                          autoComplete="new-password"
                          required
                          minLength={8}
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          className="input-field w-full"
                          placeholder="Password (min. 8 characters)"
                        />
                      </div>
                      <div>
                        <label
                          htmlFor="password_confirm"
                          className="block text-sm font-medium text-gray-700 mb-1"
                        >
                          Confirm new password
                        </label>
                        <input
                          id="password_confirm"
                          type="password"
                          autoComplete="new-password"
                          required
                          value={passwordConfirm}
                          onChange={(e) => setPasswordConfirm(e.target.value)}
                          className="input-field w-full"
                          placeholder="Repeat the new password"
                        />
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                <button
                  type="submit"
                  disabled={phoneLoading || resetLoading}
                  className="w-full flex items-center justify-center gap-2 py-3 px-4 text-sm font-medium rounded-lg text-white bg-primary hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-md"
                >
                  {phoneLoading || resetLoading ? (
                    <LoadingSpinner size="sm" />
                  ) : codeSent ? (
                    <>
                      <KeyRound className="h-4 w-4" />
                      Reset password
                    </>
                  ) : (
                    <>
                      <Phone className="h-4 w-4" />
                      Send SMS code
                    </>
                  )}
                </button>

                {codeSent && (
                  <button
                    type="button"
                    onClick={() => {
                      setCodeSent(false)
                      setCode('')
                      setNewPassword('')
                      setPasswordConfirm('')
                    }}
                    className="w-full py-2 text-sm text-gray-500 hover:text-gray-700 transition-colors"
                  >
                    Use a different number
                  </button>
                )}
              </form>
            </motion.div>
          )}
        </AnimatePresence>

        <p className="text-xs text-center text-gray-500">
          No account yet?{' '}
          <Link
            href="/register"
            className="text-primary hover:text-secondary transition-colors"
          >
            Create one
          </Link>
        </p>
      </motion.div>
    </div>
  )
}
