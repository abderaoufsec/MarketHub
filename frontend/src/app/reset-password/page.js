'use client'

import { Suspense, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { motion } from 'framer-motion'
import { KeyRound, AlertCircle, CheckCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { authAPI } from '../../lib/api'
import { apiErrorMessage, apiFieldError } from '../../lib/errors'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import { useTranslations } from 'next-intl'

// The link in the reset email carries ?uid=…&token=… — useSearchParams makes
// the route dynamic, so it needs a Suspense boundary or `next build` fails to
// prerender it (the same trap /register hit in Phase 5).
export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <ResetPasswordForm />
    </Suspense>
  )
}

function ResetPasswordForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const t = useTranslations('auth.reset')
  const uid = searchParams.get('uid') || ''
  const token = searchParams.get('token') || ''

  const [newPassword, setNewPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)

  const hasLink = Boolean(uid && token)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (newPassword !== passwordConfirm) {
      toast.error(t('passwordsDoNotMatch'))
      return
    }
    setLoading(true)
    try {
      await authAPI.resetPassword({
        uid,
        token,
        new_password: newPassword,
        new_password_confirm: passwordConfirm,
      })
      setDone(true)
      toast.success(t('resetDone'))
      setTimeout(() => router.push('/login'), 2500)
    } catch (error) {
      toast.error(
        apiFieldError(error, 'new_password') ||
          apiErrorMessage(error, t('invalidLink'))
      )
    } finally {
      setLoading(false)
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
            {t('title')}
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            {t('subtitle')}
          </p>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-white p-8 rounded-xl shadow-lg border border-gray-100"
        >
          {!hasLink ? (
            <div className="text-center space-y-4">
              <AlertCircle className="h-14 w-14 text-amber-500 mx-auto" />
              <h3 className="text-lg font-semibold text-gray-900">
                {t('missingTitle')}
              </h3>
              <p className="text-sm text-gray-600">{t('missingBody')}</p>
              <Link
                href="/forgot-password"
                className="inline-block py-2 px-4 text-sm font-medium rounded-lg text-white bg-primary hover:bg-blue-700 transition-colors shadow-md"
              >
                {t('requestNewLink')}
              </Link>
            </div>
          ) : done ? (
            <div className="text-center space-y-4">
              <CheckCircle className="h-14 w-14 text-green-500 mx-auto" />
              <h3 className="text-lg font-semibold text-gray-900">
                {t('doneTitle')}
              </h3>
              <p className="text-sm text-gray-600">{t('doneBody')}</p>
              <LoadingSpinner size="sm" />
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label
                  htmlFor="new_password"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  {t('newPasswordLabel')}
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
                  placeholder={t('passwordPlaceholder')}
                />
              </div>
              <div>
                <label
                  htmlFor="password_confirm"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  {t('confirmPasswordLabel')}
                </label>
                <input
                  id="password_confirm"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  className="input-field w-full"
                  placeholder={t('confirmPasswordPlaceholder')}
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 py-3 px-4 text-sm font-medium rounded-lg text-white bg-primary hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-md"
              >
                {loading ? (
                  <LoadingSpinner size="sm" />
                ) : (
                  <>
                    <KeyRound className="h-4 w-4" />
                    {t('submit')}
                  </>
                )}
              </button>
            </form>
          )}
        </motion.div>

        <p className="text-xs text-center text-gray-500">
          {t.rich('linkExpired', {
            link: (chunks) => (
              <Link
                href="/forgot-password"
                className="text-primary hover:text-secondary transition-colors"
              >
                {chunks}
              </Link>
            ),
          })}
        </p>
      </motion.div>
    </div>
  )
}
