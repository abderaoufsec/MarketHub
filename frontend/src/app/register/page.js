'use client'

import { Suspense, useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '../../context/AuthContext'
import { authAPI } from '../../lib/api'
import {
  apiErrorMessage,
  apiFieldError,
  apiFieldErrors,
} from '../../lib/errors'
import {
  Mail,
  Lock,
  User,
  Phone,
  AlertCircle,
  CheckCircle,
  ArrowRight,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import { useTranslations } from 'next-intl'

// `useSearchParams()` makes the route opt out of static prerendering, so the
// page must be wrapped in a Suspense boundary or `next build` fails with
// "useSearchParams() should be wrapped in a suspense boundary" (caught by the
// Phase 5 CI build step — the app had never been production-built).
export default function RegisterPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <RegisterForm />
    </Suspense>
  )
}

function RegisterForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { register } = useAuth()
  const t = useTranslations('auth.register')

  const isSeller = searchParams.get('seller') === 'true'

  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    password_confirm: '',
    first_name: '',
    last_name: '',
    phone_number: '',
    is_seller: isSeller,
  })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  // Success copy is chosen by which identity the account actually has: the
  // e2e suite asserts the exact email sentence for accounts created with an
  // email address, while phone-only accounts never receive an email.
  const [successMessage, setSuccessMessage] = useState(t('checkEmail'))
  // Phone sign-up is first-class in Phase 8: when a phone number is given we
  // offer an optional SMS verification step before submitting the account.
  // The code itself is *not* consumed here — `/auth/phone/verify/` attaches a
  // number to an already-signed-in account — it travels with the signup POST
  // and the registration serializer checks it last (see serializers.py).
  const [otpSent, setOtpSent] = useState(false)
  const [otpCode, setOtpCode] = useState('')
  const [otpBusy, setOtpBusy] = useState(false)

  // The "next: /login" nudge waits 3s so the success message reads first;
  // cancel it if the user leaves the page inside that window instead of
  // teleporting them back (same stale-timer rule as the login page).
  const redirectTimer = useRef(null)
  useEffect(() => () => clearTimeout(redirectTimer.current), [])

  const sendOtp = async () => {
    const phone = formData.phone_number.trim()
    if (!phone) {
      const errorMsg = t('enterPhoneFirst')
      setErrors({ phone_number: errorMsg })
      toast.error(errorMsg)
      return
    }
    setErrors({})
    setOtpBusy(true)
    try {
      const res = await authAPI.requestPhoneOtp({ phone_number: phone })
      setOtpSent(true)
      setOtpCode('')
      toast.success(res?.detail || t('otpSent'))
    } catch (err) {
      // Field-level message first ("This number was already requested."),
      // then the envelope message, then this page's fallback.
      const msg =
        apiFieldError(err, 'phone_number') ||
        apiErrorMessage(err, t('otpSendFailed'))
      setErrors({ phone_number: msg })
      toast.error(msg)
    } finally {
      setOtpBusy(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrors({})
    setLoading(true)

    // Validate passwords match
    if (formData.password !== formData.password_confirm) {
      const errorMsg = t('passwordsDoNotMatch')
      setErrors({ password_confirm: errorMsg })
      toast.error(errorMsg)
      setLoading(false)
      return
    }

    const phone = formData.phone_number.trim()
    const email = formData.email.trim()

    // Generate username from email (or phone) if not provided
    const registrationData = {
      ...formData,
      email,
      phone_number: phone,
    }
    if (!registrationData.username) {
      if (email) {
        registrationData.username = email.split('@')[0]
      } else if (phone) {
        registrationData.username = phone.replace(/^\+/, '')
      }
    }

    // A phone-only account has no email to fall back on, so the phone must
    // have been proven with an OTP before we can create it. With both an
    // email and a phone, either verification is accepted.
    if (!email && !phone) {
      const errorMsg = t('needEmailOrPhone')
      setErrors({ general: errorMsg })
      toast.error(errorMsg)
      setLoading(false)
      return
    }

    if (phone && !email && !otpCode.trim()) {
      const errorMsg = t('enterOtp')
      setErrors({ phone_number: errorMsg })
      toast.error(errorMsg)
      setLoading(false)
      return
    }

    // Validate password length
    if (formData.password.length < 8) {
      const errorMsg = t('passwordTooShort')
      setErrors({ password: errorMsg })
      toast.error(errorMsg)
      setLoading(false)
      return
    }

    if (phone && otpCode.trim()) {
      registrationData.otp_code = otpCode.trim()
    }

    try {
      const result = await register(registrationData)

      if (result.success) {
        const message = email ? t('checkEmail') : t('phoneVerified')
        setSuccessMessage(message)
        toast.success(t('created', { message }))
        setSuccess(true)
        redirectTimer.current = setTimeout(() => {
          router.push('/login')
        }, 3000)
      } else {
        // The envelope carries serializer messages in `details` when the
        // failure was a validation_error — render them inline, one toast per
        // field; anything else falls back to the general message.
        const fieldErrors = apiFieldErrors(result.error)
        if (Object.keys(fieldErrors).length > 0) {
          setErrors(fieldErrors)
          Object.values(fieldErrors).forEach((messages) =>
            toast.error(messages[0])
          )
        } else {
          const errorMsg = apiErrorMessage(result.error, t('failed'))
          setErrors({ general: errorMsg })
          toast.error(errorMsg)
        }
      }
    } catch (err) {
      console.error('Registration error:', err)
      const errorMsg = t('unexpectedError')
      setErrors({ general: errorMsg })
      toast.error(errorMsg)
    } finally {
      setLoading(false)
    }
  }

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setFormData({
      ...formData,
      [name]: type === 'checkbox' ? checked : value,
    })
  }

  if (success) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 py-12 px-4"
      >
        <div className="max-w-md w-full text-center">
          <motion.div
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="bg-white rounded-xl shadow-lg border border-green-200 p-8"
          >
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: 0.3, type: 'spring' }}
            >
              <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
            </motion.div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              {t('successTitle')}
            </h2>
            <p className="text-gray-600 mb-4">{successMessage}</p>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
              className="flex items-center justify-center gap-2 text-sm text-gray-500"
            >
              <LoadingSpinner size="sm" />
              <span>{t('redirecting')}</span>
            </motion.div>
          </motion.div>
        </div>
      </motion.div>
    )
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
          <h2 className="mt-6 text-center text-4xl font-bold gradient-text mb-2">
            {isSeller ? t('titleSeller') : t('title')}
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            {t.rich('haveAccount', {
              link: (chunks) => (
                <Link
                  href="/login"
                  className="font-medium text-primary hover:text-secondary transition-colors"
                >
                  {chunks}
                </Link>
              ),
            })}
          </p>
        </motion.div>

        <AnimatePresence>
          {errors.general && (
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center shadow-sm"
            >
              <AlertCircle className="h-5 w-5 me-2 flex-shrink-0" />
              <span>{errors.general}</span>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.form
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mt-8 space-y-6 bg-white p-8 rounded-xl shadow-lg border border-gray-100"
          onSubmit={handleSubmit}
        >
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 }}
              >
                <label
                  htmlFor="first_name"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  {t('firstNameLabel')}
                </label>
                <input
                  id="first_name"
                  name="first_name"
                  type="text"
                  required
                  value={formData.first_name}
                  onChange={handleChange}
                  className="input-field"
                  placeholder={t('firstNameLabel')}
                />
                {errors.first_name && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="mt-1 text-sm text-red-600"
                  >
                    {Array.isArray(errors.first_name)
                      ? errors.first_name[0]
                      : errors.first_name}
                  </motion.p>
                )}
              </motion.div>

              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4 }}
              >
                <label
                  htmlFor="last_name"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  {t('lastNameLabel')}
                </label>
                <input
                  id="last_name"
                  name="last_name"
                  type="text"
                  required
                  value={formData.last_name}
                  onChange={handleChange}
                  className="input-field"
                  placeholder={t('lastNameLabel')}
                />
                {errors.last_name && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="mt-1 text-sm text-red-600"
                  >
                    {Array.isArray(errors.last_name)
                      ? errors.last_name[0]
                      : errors.last_name}
                  </motion.p>
                )}
              </motion.div>
            </div>

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
            >
              <label
                htmlFor="email"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                {t.rich('emailLabel', {
                  hint: (chunks) => (
                    <span className="text-gray-400">{chunks}</span>
                  ),
                })}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 start-0 ps-3 flex items-center pointer-events-none">
                  <Mail className="h-5 w-5 text-gray-400" />
                </div>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  value={formData.email}
                  onChange={handleChange}
                  className="input-field ps-10"
                  placeholder={t('emailPlaceholder')}
                />
              </div>
              {errors.email && (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="mt-1 text-sm text-red-600"
                >
                  {Array.isArray(errors.email) ? errors.email[0] : errors.email}
                </motion.p>
              )}
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6 }}
            >
              <label
                htmlFor="username"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                {t('usernameLabel')}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 start-0 ps-3 flex items-center pointer-events-none">
                  <User className="h-5 w-5 text-gray-400" />
                </div>
                <input
                  id="username"
                  name="username"
                  type="text"
                  value={formData.username}
                  onChange={handleChange}
                  className="input-field ps-10"
                  placeholder={t('usernameLabel')}
                />
              </div>
              {errors.username && (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="mt-1 text-sm text-red-600"
                >
                  {Array.isArray(errors.username)
                    ? errors.username[0]
                    : errors.username}
                </motion.p>
              )}
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.65 }}
            >
              <label
                htmlFor="phone_number"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                {t.rich('phoneLabel', {
                  hint: (chunks) => (
                    <span className="text-gray-400">{chunks}</span>
                  ),
                })}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 start-0 ps-3 flex items-center pointer-events-none">
                  <Phone className="h-5 w-5 text-gray-400" />
                </div>
                <input
                  id="phone_number"
                  name="phone_number"
                  type="tel"
                  value={formData.phone_number}
                  onChange={handleChange}
                  className="input-field ps-10"
                  placeholder={t('phonePlaceholder')}
                />
              </div>
              {errors.phone_number && (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="mt-1 text-sm text-red-600"
                >
                  {Array.isArray(errors.phone_number)
                    ? errors.phone_number[0]
                    : errors.phone_number}
                </motion.p>
              )}

              {formData.phone_number.trim() && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs text-gray-600">{t('otpHint')}</p>
                    <button
                      type="button"
                      onClick={sendOtp}
                      disabled={otpBusy}
                      className="shrink-0 text-xs font-medium text-primary hover:text-secondary disabled:opacity-50"
                    >
                      {otpBusy
                        ? t('otpSending')
                        : otpSent
                          ? t('otpResend')
                          : t('otpSend')}
                    </button>
                  </div>

                  {otpSent && (
                    <div className="flex items-center gap-2">
                      <input
                        id="otp_code"
                        name="otp_code"
                        type="text"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={8}
                        value={otpCode}
                        onChange={(e) => setOtpCode(e.target.value)}
                        className="input-field"
                        placeholder={t('smsCodeLabel')}
                        aria-label={t('smsCodeLabel')}
                      />
                    </div>
                  )}
                </motion.div>
              )}
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7 }}
            >
              <label
                htmlFor="password"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                {t('passwordLabel')}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 start-0 ps-3 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-gray-400" />
                </div>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={formData.password}
                  onChange={handleChange}
                  className="input-field ps-10"
                  placeholder={t('passwordPlaceholder')}
                />
              </div>
              {errors.password && (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="mt-1 text-sm text-red-600"
                >
                  {Array.isArray(errors.password)
                    ? errors.password[0]
                    : errors.password}
                </motion.p>
              )}
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.8 }}
            >
              <label
                htmlFor="password_confirm"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                {t('confirmPasswordLabel')}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 start-0 ps-3 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-gray-400" />
                </div>
                <input
                  id="password_confirm"
                  name="password_confirm"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={formData.password_confirm}
                  onChange={handleChange}
                  className="input-field ps-10"
                  placeholder={t('confirmPasswordPlaceholder')}
                />
              </div>
              {errors.password_confirm && (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="mt-1 text-sm text-red-600"
                >
                  {Array.isArray(errors.password_confirm)
                    ? errors.password_confirm[0]
                    : errors.password_confirm}
                </motion.p>
              )}
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.9 }}
              className="flex items-center"
            >
              <input
                id="is_seller"
                name="is_seller"
                type="checkbox"
                checked={formData.is_seller}
                onChange={handleChange}
                className="h-4 w-4 text-primary focus:ring-primary border-gray-300 rounded"
              />
              <label
                htmlFor="is_seller"
                className="ms-2 block text-sm text-gray-900"
              >
                {t('asSeller')}
              </label>
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1 }}
          >
            <motion.button
              type="submit"
              disabled={loading}
              whileHover={{ scale: loading ? 1 : 1.02 }}
              whileTap={{ scale: loading ? 1 : 0.98 }}
              className="group relative w-full flex justify-center items-center gap-2 py-3 px-4 border border-transparent text-sm font-medium rounded-lg text-white bg-primary hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-xl transition-all"
            >
              {loading ? (
                <>
                  <LoadingSpinner size="sm" />
                  {t('creating')}
                </>
              ) : (
                <>
                  {t('createAccount')}
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </motion.button>
          </motion.div>

          <p className="text-xs text-center text-gray-600">
            {t.rich('terms', {
              terms: (chunks) => (
                <Link
                  href="/terms"
                  className="text-primary hover:text-secondary transition-colors"
                >
                  {chunks}
                </Link>
              ),
              privacy: (chunks) => (
                <Link
                  href="/privacy"
                  className="text-primary hover:text-secondary transition-colors"
                >
                  {chunks}
                </Link>
              ),
            })}
          </p>
        </motion.form>
      </motion.div>
    </div>
  )
}
