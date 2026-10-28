'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { useAuth } from '../../context/AuthContext'
import { authAPI } from '../../lib/api'
import { apiErrorMessage, apiFieldError } from '../../lib/errors'
import { Mail, Phone, Save, AlertCircle, CheckCircle, Lock } from 'lucide-react'

/**
 * Phase 11 of docs/todo.md: the backend keys emails/SMS off the user's
 * `preferred_language`. The options are *native* language names (العربية /
 * Français / English) in every UI locale — you pick a language by the name
 * speakers of that language use, so these three strings are never translated.
 */
const LANGUAGE_OPTIONS = [
  { value: 'ar', label: 'العربية' },
  { value: 'fr', label: 'Français' },
  { value: 'en', label: 'English' },
]

export default function ProfilePage() {
  const router = useRouter()
  const t = useTranslations('profile')
  const {
    user,
    isAuthenticated,
    loading: authLoading,
    updateProfile,
  } = useAuth()
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    phone_number: '',
    email: '',
    // The API default is 'fr'; never send an empty value.
    preferred_language: 'fr',
  })
  // Inline change-password form on the security card. The button here used to
  // have no onClick at all — a dead affordance in a security card is worse
  // than none, so it now drives a real form backed by
  // POST /api/v1/auth/change-password/ (Phase 7).
  const [passwordFormOpen, setPasswordFormOpen] = useState(false)
  const [passwordLoading, setPasswordLoading] = useState(false)
  const [passwordMessage, setPasswordMessage] = useState(null)
  const [passwords, setPasswords] = useState({
    old_password: '',
    new_password: '',
    new_password_confirm: '',
  })

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, router])

  useEffect(() => {
    if (user) {
      setFormData({
        first_name: user.first_name || '',
        last_name: user.last_name || '',
        phone_number: user.phone_number || '',
        email: user.email || '',
        preferred_language: user.preferred_language || 'fr',
      })
    }
  }, [user])

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    try {
      setLoading(true)
      setMessage(null)
      const result = await updateProfile(formData)
      if (result.success) {
        setMessage({ type: 'success', text: t('updateSuccess') })
      } else {
        setMessage({
          type: 'error',
          // AuthContext failures are Phase 9 envelopes — `message` is the
          // text to show (already seeded with this action's fallback).
          text: apiErrorMessage(result.error, t('updateFailed')),
        })
      }
    } catch (error) {
      console.error('Error updating profile:', error)
      setMessage({
        type: 'error',
        text: apiErrorMessage(error, t('updateFailed')),
      })
    } finally {
      setLoading(false)
    }
  }

  const handlePasswordSubmit = async (e) => {
    e.preventDefault()
    setPasswordMessage(null)
    if (passwords.new_password !== passwords.new_password_confirm) {
      setPasswordMessage({
        type: 'error',
        text: t('security.passwordsDoNotMatch'),
      })
      return
    }
    try {
      setPasswordLoading(true)
      await authAPI.changePassword(passwords)
      // Every other session is revoked server-side and this device gets a
      // fresh cookie pair; collapse the form and confirm inline.
      setPasswordMessage({
        type: 'success',
        text: t('security.changePasswordSuccess'),
      })
      setPasswords({
        old_password: '',
        new_password: '',
        new_password_confirm: '',
      })
      setPasswordFormOpen(false)
    } catch (error) {
      setPasswordMessage({
        type: 'error',
        // Field errors win over the envelope message: the wrong-current-
        // password case carries the `old_password_incorrect` code (Phase 7)
        // and a mismatch/validation lands on the new-password field.
        text:
          apiFieldError(error, 'old_password') ||
          apiFieldError(error, 'new_password') ||
          apiErrorMessage(error, t('security.changePasswordFailed')),
      })
    } finally {
      setPasswordLoading(false)
    }
  }

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">{t('title')}</h1>
        <p className="text-gray-600 mt-1">{t('subtitle')}</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Sidebar */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div className="text-center">
              <div className="bg-primary text-white rounded-full h-24 w-24 mx-auto mb-4 flex items-center justify-center text-3xl font-bold">
                {user?.first_name?.charAt(0)?.toUpperCase() ||
                  user?.email?.charAt(0)?.toUpperCase() ||
                  'U'}
              </div>
              <h3 className="text-lg font-semibold text-gray-900">
                {user?.first_name && user?.last_name
                  ? `${user.first_name} ${user.last_name}`
                  : user?.email}
              </h3>
              <p className="text-sm text-gray-600 mt-1">{user?.email}</p>
              {user?.is_seller && (
                <span className="inline-block mt-3 px-3 py-1 bg-primary/10 text-primary rounded-full text-sm font-medium">
                  {t('sellerAccount')}
                </span>
              )}
            </div>

            <div className="mt-6 pt-6 border-t border-gray-200 space-y-2">
              <div className="flex items-center text-sm text-gray-600">
                <Mail className="h-4 w-4 me-2" />
                <span className="truncate">{user?.email}</span>
              </div>
              {user?.phone_number && (
                <div className="flex items-center text-sm text-gray-600">
                  <Phone className="h-4 w-4 me-2" />
                  <span>{user.phone_number}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Personal Information */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-6">
              {t('personalInfo')}
            </h2>

            {message && (
              <div
                className={`mb-6 p-4 rounded-lg flex items-center ${
                  message.type === 'success'
                    ? 'bg-green-50 border border-green-200 text-green-700'
                    : 'bg-red-50 border border-red-200 text-red-700'
                }`}
              >
                {message.type === 'success' ? (
                  <CheckCircle className="h-5 w-5 me-2 flex-shrink-0" />
                ) : (
                  <AlertCircle className="h-5 w-5 me-2 flex-shrink-0" />
                )}
                <span>{message.text}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label
                    htmlFor="first_name"
                    className="block text-sm font-medium text-gray-700 mb-2"
                  >
                    {t('fields.firstName')}
                  </label>
                  <input
                    type="text"
                    id="first_name"
                    name="first_name"
                    value={formData.first_name}
                    onChange={handleChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
                    placeholder={t('fields.firstNamePlaceholder')}
                  />
                </div>

                <div>
                  <label
                    htmlFor="last_name"
                    className="block text-sm font-medium text-gray-700 mb-2"
                  >
                    {t('fields.lastName')}
                  </label>
                  <input
                    type="text"
                    id="last_name"
                    name="last_name"
                    value={formData.last_name}
                    onChange={handleChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
                    placeholder={t('fields.lastNamePlaceholder')}
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="email"
                  className="block text-sm font-medium text-gray-700 mb-2"
                >
                  {t('fields.email')}
                </label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  disabled
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500 cursor-not-allowed"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {t('fields.emailLocked')}
                </p>
              </div>

              <div>
                <label
                  htmlFor="phone_number"
                  className="block text-sm font-medium text-gray-700 mb-2"
                >
                  {t('fields.phone')}
                </label>
                <input
                  type="tel"
                  id="phone_number"
                  name="phone_number"
                  value={formData.phone_number}
                  onChange={handleChange}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
                  placeholder={t('fields.phonePlaceholder')}
                />
              </div>

              <div>
                <label
                  htmlFor="preferred_language"
                  className="block text-sm font-medium text-gray-700 mb-2"
                >
                  {t('fields.preferredLanguage')}
                </label>
                <select
                  id="preferred_language"
                  name="preferred_language"
                  value={formData.preferred_language}
                  onChange={handleChange}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
                >
                  {LANGUAGE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  {t('fields.preferredLanguageHint')}
                </p>
              </div>

              <div className="pt-4 border-t">
                <button
                  type="submit"
                  disabled={loading}
                  className="btn-primary flex items-center gap-2 disabled:opacity-50"
                >
                  <Save className="h-5 w-5" />
                  {loading ? t('save.saving') : t('save.submit')}
                </button>
              </div>
            </form>
          </div>

          {/* Security Section */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              {t('security.title')}
            </h2>
            <div className="space-y-4">
              {passwordMessage && (
                <div
                  className={`flex items-center gap-2 p-3 rounded-lg text-sm ${
                    passwordMessage.type === 'success'
                      ? 'bg-green-50 text-green-700'
                      : 'bg-red-50 text-red-700'
                  }`}
                >
                  {passwordMessage.type === 'success' ? (
                    <CheckCircle className="h-4 w-4 shrink-0" />
                  ) : (
                    <AlertCircle className="h-4 w-4 shrink-0" />
                  )}
                  <span>{passwordMessage.text}</span>
                </div>
              )}
              <div className="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
                <div className="flex items-center gap-3">
                  <div className="bg-gray-100 p-2 rounded-lg">
                    <Lock className="h-5 w-5 text-gray-600" />
                  </div>
                  <div>
                    <p className="font-medium text-gray-900">
                      {t('security.changePassword')}
                    </p>
                    <p className="text-sm text-gray-600">
                      {t('security.changePasswordText')}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setPasswordMessage(null)
                    setPasswordFormOpen((open) => !open)
                  }}
                  aria-expanded={passwordFormOpen}
                  className="text-primary hover:text-secondary font-medium text-sm"
                >
                  {passwordFormOpen
                    ? t('security.cancel')
                    : t('security.change')}
                </button>
              </div>

              {passwordFormOpen && (
                <form
                  onSubmit={handlePasswordSubmit}
                  className="space-y-3 p-4 border border-gray-200 rounded-lg"
                >
                  <div>
                    <label
                      htmlFor="old_password"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      {t('security.currentPasswordLabel')}
                    </label>
                    <input
                      id="old_password"
                      type="password"
                      autoComplete="current-password"
                      required
                      value={passwords.old_password}
                      onChange={(e) =>
                        setPasswords((prev) => ({
                          ...prev,
                          old_password: e.target.value,
                        }))
                      }
                      className="input-field w-full"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="new_password"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      {t('security.newPasswordLabel')}
                    </label>
                    <input
                      id="new_password"
                      type="password"
                      autoComplete="new-password"
                      required
                      minLength={8}
                      value={passwords.new_password}
                      onChange={(e) =>
                        setPasswords((prev) => ({
                          ...prev,
                          new_password: e.target.value,
                        }))
                      }
                      className="input-field w-full"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="new_password_confirm"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      {t('security.confirmPasswordLabel')}
                    </label>
                    <input
                      id="new_password_confirm"
                      type="password"
                      autoComplete="new-password"
                      required
                      minLength={8}
                      value={passwords.new_password_confirm}
                      onChange={(e) =>
                        setPasswords((prev) => ({
                          ...prev,
                          new_password_confirm: e.target.value,
                        }))
                      }
                      className="input-field w-full"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={passwordLoading}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg text-white bg-primary hover:bg-blue-700 disabled:opacity-50 transition-colors"
                  >
                    <Save className="h-4 w-4" />
                    {passwordLoading
                      ? t('security.submitting')
                      : t('security.submit')}
                  </button>
                </form>
              )}
            </div>
          </div>

          {/* Account Actions */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              {t('actions.title')}
            </h2>
            <div className="space-y-3">
              {user?.is_seller && (
                <button
                  onClick={() => router.push('/seller/dashboard')}
                  className="w-full text-start px-4 py-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  <span className="font-medium text-gray-900">
                    {t('actions.sellerDashboard')}
                  </span>
                  <p className="text-sm text-gray-600 mt-1">
                    {t('actions.sellerDashboardText')}
                  </p>
                </button>
              )}
              <button
                onClick={() => router.push('/orders')}
                className="w-full text-start px-4 py-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <span className="font-medium text-gray-900">
                  {t('actions.orderHistory')}
                </span>
                <p className="text-sm text-gray-600 mt-1">
                  {t('actions.orderHistoryText')}
                </p>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
