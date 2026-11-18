'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import {
  AlertCircle,
  BadgeCheck,
  CheckCircle,
  Clock,
  ShieldCheck,
  Store,
  Upload,
} from 'lucide-react'
import { useTranslations } from 'next-intl'
import toast from 'react-hot-toast'

import LoadingSpinner from '../../../components/common/LoadingSpinner'
import SellerBadge from '../../../components/trust/SellerBadge'
import { useAuth } from '../../../context/AuthContext'
import { mediaAPI, trustAPI } from '../../../lib/api'
import { apiErrorMessage } from '../../../lib/errors'

const ID_TYPES = ['ID_CARD', 'PASSPORT', 'DRIVING_LICENSE']

function StatusPill({ status, t }) {
  const map = {
    PENDING: { icon: Clock, cls: 'bg-amber-50 text-amber-700' },
    APPROVED: { icon: CheckCircle, cls: 'bg-emerald-50 text-emerald-700' },
    REJECTED: { icon: AlertCircle, cls: 'bg-red-50 text-red-700' },
  }
  const entry = map[status] || map.PENDING
  const Icon = entry.icon
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${entry.cls}`}
    >
      <Icon className="h-3 w-3" />
      {t(status.toLowerCase())}
    </span>
  )
}

/**
 * Seller verification (Phase 17).
 *
 * Everything here is a *submission*: the badge is granted only after a staff
 * member approves the row, so this page never claims a verification is live.
 * The private document photo is uploaded through the Phase 14 media pipeline
 * and referenced by id, never sent as base64 in the JSON body.
 */
export default function VerificationPage() {
  const t = useTranslations('trust.verification')
  const { isAuthenticated, loading: authLoading, user } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const [documentType, setDocumentType] = useState('ID_CARD')
  const [documentNumber, setDocumentNumber] = useState('')
  const [imageId, setImageId] = useState(null)
  const [uploading, setUploading] = useState(false)

  const [showStore, setShowStore] = useState(false)
  const [commercialRegister, setCommercialRegister] = useState('')
  const [nif, setNif] = useState('')

  const fileRef = useRef(null)

  const load = useCallback(() => {
    trustAPI
      .myVerifications()
      .then((response) => setRows(response.data || []))
      .catch(() => toast.error(t('submitError')))
      .finally(() => setLoading(false))
  }, [t])

  useEffect(() => {
    if (authLoading) return
    if (!isAuthenticated) {
      setLoading(false)
      return
    }
    load()
  }, [authLoading, isAuthenticated, load])

  if (authLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <LoadingSpinner />
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <ShieldCheck className="mx-auto mb-4 h-10 w-10 text-gray-400" />
        <p className="mb-4 text-gray-600">{t('loginRequired')}</p>
        <Link
          href="/login"
          className="rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white"
        >
          {t('login')}
        </Link>
      </div>
    )
  }

  const uploadPhoto = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const response = await mediaAPI.upload(file)
      setImageId(response.data.id)
    } catch (error) {
      toast.error(apiErrorMessage(error, t('submitError')))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const submitIdentity = async (event) => {
    event.preventDefault()
    if (!imageId) {
      toast.error(t('photo'))
      return
    }
    setBusy(true)
    try {
      await trustAPI.submitIdentity({
        document_image_id: imageId,
        document_type: documentType,
        document_number: documentNumber,
      })
      toast.success(t('submitted'))
      setImageId(null)
      setDocumentNumber('')
      load()
    } catch (error) {
      toast.error(apiErrorMessage(error, t('submitError')))
    } finally {
      setBusy(false)
    }
  }

  const submitStore = async (event) => {
    event.preventDefault()
    setBusy(true)
    try {
      await trustAPI.submitStore({
        commercial_register_number: commercialRegister,
        nif_number: nif,
      })
      toast.success(t('storeSubmitted'))
      setCommercialRegister('')
      setNif('')
      setShowStore(false)
      load()
    } catch (error) {
      toast.error(apiErrorMessage(error, t('submitError')))
    } finally {
      setBusy(false)
    }
  }

  const badges = [
    user?.phone_verified ? { code: 'PHONE' } : null,
    rows.some((row) => row.kind === 'IDENTITY' && row.status === 'APPROVED')
      ? { code: 'ID' }
      : null,
    rows.some((row) => row.kind === 'STORE' && row.status === 'APPROVED')
      ? { code: 'STORE' }
      : null,
  ].filter(Boolean)

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">{t('title')}</h1>
        <p className="mt-2 text-gray-600">{t('subtitle')}</p>
        <div className="mt-4">
          <SellerBadge badges={badges} showUnverified />
        </div>
        {!user?.phone_verified && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {t('phoneRequired')}
          </p>
        )}
      </header>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-gray-900">
          {t('statusTitle')}
        </h2>
        {loading ? (
          <LoadingSpinner />
        ) : rows.length === 0 ? (
          <p className="rounded-xl border border-gray-100 bg-gray-50 p-4 text-sm text-gray-500">
            {t('empty')}
          </p>
        ) : (
          <ul className="space-y-3">
            {rows.map((row) => (
              <li
                key={row.id}
                className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-gray-900">
                    {row.kind_label || row.kind}
                  </span>
                  <StatusPill status={row.status} t={t} />
                </div>
                {row.store_name && (
                  <p className="mt-1 text-sm text-gray-500">{row.store_name}</p>
                )}
                {row.status === 'REJECTED' && row.rejection_reason && (
                  <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                    {t('rejectionReason')}: {row.rejection_reason}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mb-8 rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
        <h2 className="mb-1 flex items-center gap-2 text-lg font-semibold text-gray-900">
          <BadgeCheck className="h-5 w-5 text-blue-600" />
          {t('submitTitle')}
        </h2>
        <p className="mb-4 text-sm text-gray-600">{t('submitHint')}</p>

        <form onSubmit={submitIdentity} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-gray-700">
                {t('documentType')}
              </span>
              <select
                value={documentType}
                onChange={(event) => setDocumentType(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2"
              >
                {ID_TYPES.map((value) => (
                  <option key={value} value={value}>
                    {t(`types.${value}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-gray-700">
                {t('documentNumber')}
              </span>
              <input
                value={documentNumber}
                onChange={(event) => setDocumentNumber(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2"
                maxLength={64}
              />
            </label>
          </div>

          <div>
            <span className="mb-1 block text-sm font-medium text-gray-700">
              {t('photo')}
            </span>
            <div className="flex flex-wrap items-center gap-3">
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={uploadPhoto}
                className="hidden"
                id="verification-photo"
              />
              <label
                htmlFor="verification-photo"
                className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                <Upload className="h-4 w-4" />
                {uploading ? t('uploading') : t('upload')}
              </label>
              {imageId && (
                <span className="inline-flex items-center gap-1 text-sm text-emerald-600">
                  <CheckCircle className="h-4 w-4" />#{imageId}
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-gray-400">{t('photoHint')}</p>
          </div>

          <button
            type="submit"
            disabled={busy || uploading}
            className="rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white hover:bg-primary-600 disabled:opacity-60"
          >
            {busy ? t('submitting') : t('submit')}
          </button>
        </form>
      </section>

      <section className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
        <h2 className="mb-1 flex items-center gap-2 text-lg font-semibold text-gray-900">
          <Store className="h-5 w-5 text-emerald-600" />
          {t('storeTitle')}
        </h2>
        <p className="mb-4 text-sm text-gray-600">{t('storeHint')}</p>
        {showStore ? (
          <form onSubmit={submitStore} className="space-y-4">
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-gray-700">
                {t('commercialRegister')}
              </span>
              <input
                value={commercialRegister}
                onChange={(event) => setCommercialRegister(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2"
                maxLength={64}
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-gray-700">
                {t('nif')}
              </span>
              <input
                value={nif}
                onChange={(event) => setNif(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2"
                maxLength={64}
              />
            </label>
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={busy}
                className="rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white hover:bg-primary-600 disabled:opacity-60"
              >
                {busy ? t('submitting') : t('storeSubmit')}
              </button>
              <button
                type="button"
                onClick={() => setShowStore(false)}
                className="rounded-xl border border-gray-300 px-5 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                {t('cancel')}
              </button>
            </div>
          </form>
        ) : (
          <button
            type="button"
            onClick={() => setShowStore(true)}
            className="rounded-xl border border-gray-300 px-5 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50"
          >
            {t('storeTitle')}
          </button>
        )}
      </section>
    </div>
  )
}
