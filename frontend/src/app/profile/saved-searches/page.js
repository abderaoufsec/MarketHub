'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  ArrowRight,
  Bookmark,
  Mail,
  MessageCircle,
  Pause,
  Phone,
  Play,
  Trash2,
} from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import toast from 'react-hot-toast'

import LoadingSpinner from '../../../components/common/LoadingSpinner'
import { useAuth } from '../../../context/AuthContext'
import { searchAPI } from '../../../lib/api'

/**
 * Saved searches - the "watch this search" side of Phase 15.
 *
 * Each row is the *same* query string the search page uses, so "open" is a
 * plain link; pausing only flips `is_active`, which both the instant signal
 * and the daily digest honour.
 */
export default function SavedSearchesPage() {
  const t = useTranslations('savedSearches')
  const locale = useLocale()
  const { isAuthenticated, loading: authLoading } = useAuth()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [busyId, setBusyId] = useState(null)

  useEffect(() => {
    if (authLoading) return
    if (!isAuthenticated) {
      setLoading(false)
      return
    }
    let cancelled = false
    searchAPI
      .savedList()
      .then((response) => {
        if (!cancelled) setItems(response.data || [])
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [authLoading, isAuthenticated])

  const toggle = async (row) => {
    setBusyId(row.id)
    try {
      const response = await searchAPI.updateSaved(row.id, {
        is_active: !row.is_active,
      })
      setItems((prev) =>
        prev.map((item) => (item.id === row.id ? response.data : item))
      )
      toast.success(response.data.is_active ? t('resumed') : t('paused'))
    } catch {
      toast.error(t('updateError'))
    } finally {
      setBusyId(null)
    }
  }

  const remove = async (row) => {
    if (!window.confirm(t('confirmDelete'))) return
    setBusyId(row.id)
    try {
      await searchAPI.deleteSaved(row.id)
      setItems((prev) => prev.filter((item) => item.id !== row.id))
      toast.success(t('deleted'))
    } catch {
      toast.error(t('deleteError'))
    } finally {
      setBusyId(null)
    }
  }

  if (authLoading || loading) return <LoadingSpinner />

  if (!isAuthenticated) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <Bookmark className="h-12 w-12 mx-auto text-gray-300 mb-4" />
        <h1 className="text-3xl font-bold text-gray-900 mb-3">{t('title')}</h1>
        <p className="text-gray-600 mb-6">{t('loginRequired')}</p>
        <Link
          href="/login?next=/profile/saved-searches"
          className="btn-primary"
        >
          {t('signIn')}
        </Link>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <p className="text-gray-600">{t('loadError')}</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="btn-secondary mt-4"
        >
          {t('retry')}
        </button>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-8">
        <div>
          <h1 className="text-3xl font-bold gradient-text">{t('title')}</h1>
          <p className="text-gray-600 mt-1">{t('subtitle')}</p>
        </div>
        <Link href="/search" className="btn-secondary text-sm">
          {t('newSearch')}
        </Link>
      </div>

      {items.length === 0 ? (
        <div className="bg-white border border-gray-100 rounded-xl shadow-sm p-10 text-center">
          <Bookmark className="h-10 w-10 mx-auto text-gray-300 mb-3" />
          <p className="text-gray-600 mb-5">{t('empty')}</p>
          <Link
            href="/search"
            className="btn-primary inline-flex items-center gap-2"
          >
            {t('startSearching')}
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((row) => (
            <div
              key={row.id}
              className={`bg-white border rounded-xl shadow-sm p-4 sm:p-5 ${
                row.is_active
                  ? 'border-gray-100'
                  : 'border-dashed border-gray-200'
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-semibold text-gray-900 truncate">
                      {row.name || row.params?.q || t('filtersOnly')}
                    </h2>
                    <span
                      className={`text-xs rounded-full px-2 py-0.5 ${
                        row.is_active
                          ? 'bg-green-50 text-green-700'
                          : 'bg-gray-100 text-gray-500'
                      }`}
                    >
                      {row.is_active ? t('active') : t('paused')}
                    </span>
                    <span className="text-xs rounded-full bg-primary/10 text-primary px-2 py-0.5">
                      {t(`frequencies.${row.frequency}`)}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500 mt-1 truncate">
                    {row.query_string || t('filtersOnly')}
                  </p>
                  <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-gray-500">
                    {row.notify_email && (
                      <span className="inline-flex items-center gap-1">
                        <Mail className="h-3.5 w-3.5" />
                        {t('channels.email')}
                      </span>
                    )}
                    {row.notify_sms && (
                      <span className="inline-flex items-center gap-1">
                        <Phone className="h-3.5 w-3.5" />
                        {t('channels.sms')}
                      </span>
                    )}
                    {row.notify_whatsapp && (
                      <span className="inline-flex items-center gap-1">
                        <MessageCircle className="h-3.5 w-3.5" />
                        {t('channels.whatsapp')}
                      </span>
                    )}
                    <span>
                      {row.last_notified_at
                        ? t('lastNotified', {
                            date: new Intl.DateTimeFormat(locale, {
                              dateStyle: 'medium',
                              timeStyle: 'short',
                            }).format(new Date(row.last_notified_at)),
                          })
                        : t('neverNotified')}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Link
                    href={`/search?${row.query_string}`}
                    className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                  >
                    {t('open')}
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                  <button
                    type="button"
                    onClick={() => toggle(row)}
                    disabled={busyId === row.id}
                    title={row.is_active ? t('pause') : t('resume')}
                    aria-label={row.is_active ? t('pause') : t('resume')}
                    className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 disabled:opacity-50"
                  >
                    {row.is_active ? (
                      <Pause className="h-4 w-4" />
                    ) : (
                      <Play className="h-4 w-4" />
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(row)}
                    disabled={busyId === row.id}
                    title={t('delete')}
                    aria-label={t('delete')}
                    className="p-2 rounded-lg text-red-500 hover:bg-red-50 disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
