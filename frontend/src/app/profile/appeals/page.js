'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { AlertCircle, CheckCircle, Clock, Gavel, Send } from 'lucide-react'
import { useTranslations } from 'next-intl'
import toast from 'react-hot-toast'

import LoadingSpinner from '../../../components/common/LoadingSpinner'
import { useAuth } from '../../../context/AuthContext'
import { productsAPI, reviewsAPI, trustAPI } from '../../../lib/api'
import { apiErrorMessage } from '../../../lib/errors'

const KINDS = ['LISTING', 'REVIEW', 'ACCOUNT']

const STATUS_STYLES = {
  OPEN: 'bg-amber-50 text-amber-700',
  APPROVED: 'bg-emerald-50 text-emerald-700',
  REJECTED: 'bg-red-50 text-red-700',
}

/**
 * Appeals (Phase 17).
 *
 * One page for the three appealable decisions - a rejected/archived listing,
 * a review that was hidden, and a suspended account. The server re-checks the
 * target's state and ownership on submit, so the dropdowns here are only a
 * convenience, never the authority.
 */
export default function AppealsPage() {
  const t = useTranslations('trust.appeals')
  const { isAuthenticated, loading: authLoading } = useAuth()
  const [appeals, setAppeals] = useState([])
  const [listings, setListings] = useState([])
  const [reviews, setReviews] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const [kind, setKind] = useState('LISTING')
  const [listingId, setListingId] = useState('')
  const [reviewId, setReviewId] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (authLoading) return
    if (!isAuthenticated) {
      setLoading(false)
      return
    }
    let cancelled = false
    Promise.allSettled([
      trustAPI.appeals(),
      productsAPI.sellerList({ status: 'REJECTED' }),
      reviewsAPI.myReviews(),
    ]).then(([appealsResult, listingsResult, reviewsResult]) => {
      if (cancelled) return
      if (appealsResult.status === 'fulfilled') {
        setAppeals(appealsResult.value.data || [])
      }
      if (listingsResult.status === 'fulfilled') {
        setListings(
          listingsResult.value.data?.results || listingsResult.value.data || []
        )
      }
      if (reviewsResult.status === 'fulfilled') {
        const rows =
          reviewsResult.value.data?.results || reviewsResult.value.data || []
        setReviews(rows.filter((row) => row.is_approved === false))
      }
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [authLoading, isAuthenticated])

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
        <Gavel className="mx-auto mb-4 h-10 w-10 text-gray-400" />
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

  const submit = async (event) => {
    event.preventDefault()
    const payload = { kind, message: message.trim() }
    if (kind === 'LISTING') payload.listing_id = Number(listingId)
    if (kind === 'REVIEW') payload.review_id = Number(reviewId)

    setBusy(true)
    try {
      const response = await trustAPI.createAppeal(payload)
      setAppeals((prev) => [response.data, ...prev])
      setMessage('')
      setListingId('')
      setReviewId('')
      toast.success(t('submitted'))
    } catch (error) {
      toast.error(apiErrorMessage(error, t('submitError')))
    } finally {
      setBusy(false)
    }
  }

  const canSubmit =
    message.trim().length > 0 &&
    (kind !== 'LISTING' || listingId) &&
    (kind !== 'REVIEW' || reviewId)

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">{t('title')}</h1>
        <p className="mt-2 text-gray-600">{t('subtitle')}</p>
      </header>

      <section className="mb-8 rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-gray-900">
          <Gavel className="h-5 w-5 text-primary" />
          {t('newTitle')}
        </h2>
        <form onSubmit={submit} className="space-y-4">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-gray-700">
              {t('kind')}
            </span>
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            >
              {KINDS.map((value) => (
                <option key={value} value={value}>
                  {t(`kinds.${value}`)}
                </option>
              ))}
            </select>
          </label>

          {kind === 'LISTING' && (
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-gray-700">
                {t('listing')}
              </span>
              <select
                value={listingId}
                onChange={(event) => setListingId(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2"
              >
                <option value="">{t('chooseListing')}</option>
                {listings.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          {kind === 'REVIEW' && (
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-gray-700">
                {t('review')}
              </span>
              <select
                value={reviewId}
                onChange={(event) => setReviewId(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2"
              >
                <option value="">{t('chooseReview')}</option>
                {reviews.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.product_name || `#${row.product}`} — {row.rating}★
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="block text-sm">
            <span className="mb-1 block font-medium text-gray-700">
              {t('message')}
            </span>
            <textarea
              rows={4}
              maxLength={4000}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={t('messagePlaceholder')}
              className="w-full rounded-lg border border-gray-300 px-3 py-2"
            />
          </label>

          <button
            type="submit"
            disabled={busy || !canSubmit}
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white hover:bg-primary-600 disabled:opacity-60"
          >
            <Send className="h-4 w-4" />
            {busy ? t('submitting') : t('submit')}
          </button>
        </form>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-gray-900">
          {t('title')}
        </h2>
        {loading ? (
          <LoadingSpinner />
        ) : appeals.length === 0 ? (
          <p className="rounded-xl border border-gray-100 bg-gray-50 p-4 text-sm text-gray-500">
            {t('empty')}
          </p>
        ) : (
          <ul className="space-y-3">
            {appeals.map((appeal) => (
              <li
                key={appeal.id}
                className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-gray-900">
                    {appeal.kind_label || appeal.kind}
                    {appeal.listing_name ? ` — ${appeal.listing_name}` : ''}
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
                      STATUS_STYLES[appeal.status] ||
                      'bg-gray-100 text-gray-700'
                    }`}
                  >
                    {appeal.status === 'OPEN' ? (
                      <Clock className="h-3 w-3" />
                    ) : appeal.status === 'APPROVED' ? (
                      <CheckCircle className="h-3 w-3" />
                    ) : (
                      <AlertCircle className="h-3 w-3" />
                    )}
                    {appeal.status_label || appeal.status}
                  </span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm text-gray-600">
                  {appeal.message}
                </p>
                <p className="mt-3 border-t border-gray-100 pt-2 text-xs text-gray-500">
                  {t('resolution')}: {appeal.resolution || t('noResolution')}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
