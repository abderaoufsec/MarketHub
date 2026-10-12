'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { motion } from 'framer-motion'
import { CheckCircle, XCircle, AlertCircle, Mail } from 'lucide-react'
import { authAPI } from '../../../../lib/api'
import LoadingSpinner from '../../../../components/common/LoadingSpinner'

/**
 * Landing page for the link in the verification email:
 * /verify-email/[uidb64]/[token]/ (Phase 8 of docs/todo.md — the page the
 * backend has always mailed, now actually built).
 *
 * States: verifying → verified | failed. A wrong/expired token is reported
 * honestly with a "resend" way out instead of a dead end.
 */
export default function VerifyEmailPage() {
  const { uidb64, token } = useParams()
  const [status, setStatus] = useState('verifying') // verifying | ok | error
  const [message, setMessage] = useState('')
  const [resendEmail, setResendEmail] = useState('')
  const [resent, setResent] = useState(false)
  const [resendLoading, setResendLoading] = useState(false)
  const started = useRef(false)

  useEffect(() => {
    // React 18 StrictMode runs effects twice in dev — never verify twice
    // (the second call would report a consumed token as a failure).
    if (started.current) return
    started.current = true

    authAPI
      .verifyEmail(uidb64, token)
      .then(() => {
        setStatus('ok')
        setMessage('Your email address is verified — you can sign in now.')
      })
      .catch((error) => {
        setStatus('error')
        setMessage(
          error.response?.data?.error ||
            'This verification link is invalid or has expired.'
        )
      })
  }, [uidb64, token])

  const handleResend = async (e) => {
    e.preventDefault()
    if (!resendEmail) return
    setResendLoading(true)
    try {
      // Enumeration-safe: the endpoint answers 200 whether or not the
      // address exists, so there is nothing to interpret here.
      await authAPI.resendVerification({ email: resendEmail })
      setResent(true)
    } catch {
      // Same generic reply on a throttle/validation error — the form stays.
      setResent(true)
    } finally {
      setResendLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 py-12 px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="max-w-md w-full bg-white rounded-xl shadow-lg border border-gray-100 p-8 text-center"
      >
        {status === 'verifying' && (
          <>
            <LoadingSpinner size="lg" />
            <h2 className="mt-6 text-2xl font-bold text-gray-900">
              Verifying your email…
            </h2>
            <p className="mt-2 text-sm text-gray-600">
              One moment while we confirm your address.
            </p>
          </>
        )}

        {status === 'ok' && (
          <motion.div
            initial={{ scale: 0.9 }}
            animate={{ scale: 1 }}
            transition={{ type: 'spring' }}
          >
            <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              Email verified!
            </h2>
            <p className="text-gray-600 mb-6">{message}</p>
            <Link
              href="/login"
              className="inline-flex items-center gap-2 py-3 px-6 text-sm font-medium rounded-lg text-white bg-primary hover:bg-blue-700 transition-colors shadow-md"
            >
              Sign in
            </Link>
          </motion.div>
        )}

        {status === 'error' && (
          <motion.div
            initial={{ scale: 0.9 }}
            animate={{ scale: 1 }}
            transition={{ type: 'spring' }}
          >
            <XCircle className="h-16 w-16 text-red-500 mx-auto mb-4" />
            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              Verification failed
            </h2>
            <p className="text-gray-600 mb-6">{message}</p>

            <div className="space-y-3">
              {resent ? (
                <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg flex items-center justify-center gap-2 text-sm">
                  <Mail className="h-4 w-4" />
                  If that account still needs verification, a new link is on its
                  way.
                </div>
              ) : (
                <form onSubmit={handleResend} className="space-y-3">
                  <input
                    type="email"
                    required
                    autoComplete="email"
                    value={resendEmail}
                    onChange={(e) => setResendEmail(e.target.value)}
                    className="input-field w-full"
                    placeholder="Your email address"
                    aria-label="Your email address"
                  />
                  <button
                    type="submit"
                    disabled={resendLoading}
                    className="w-full inline-flex items-center justify-center gap-2 py-3 px-4 text-sm font-medium rounded-lg text-white bg-primary hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-md"
                  >
                    {resendLoading ? (
                      <LoadingSpinner size="sm" />
                    ) : (
                      <>
                        <AlertCircle className="h-4 w-4" />
                        Resend verification email
                      </>
                    )}
                  </button>
                </form>
              )}
              <Link
                href="/login"
                className="block w-full py-3 px-4 text-sm font-medium rounded-lg text-gray-700 bg-gray-100 hover:bg-gray-200 transition-colors"
              >
                Back to sign in
              </Link>
            </div>
          </motion.div>
        )}
      </motion.div>
    </div>
  )
}
