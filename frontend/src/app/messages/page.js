'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import {
  Archive,
  ArchiveRestore,
  Inbox,
  Loader2,
  MessageSquare,
  ShieldCheck,
} from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import { messagingAPI } from '../../lib/api'
import { apiErrorMessage } from '../../lib/errors'
import { useAuth } from '../../context/AuthContext'
import { formatTimestamp, messagePreview } from '../../lib/messaging'
import SafeImage from '../../components/common/SafeImage'

const FILTERS = [
  { key: 'all', params: {} },
  { key: 'buying', params: { role: 'buyer' } },
  { key: 'selling', params: { role: 'seller' } },
  { key: 'archived', params: { archived: 1 } },
]

/**
 * The buyer/seller inbox (Phase 16).
 *
 * One list for both sides of the marketplace: the API returns the caller's
 * role on each row, and the tabs only add the `role`/`archived` filters. The
 * list polls while open, so a new message updates the unread badge without a
 * websocket; Phase 22 can swap the transport behind the same API.
 */
export default function MessagesPage() {
  const t = useTranslations('messages')
  const locale = useLocale()
  const { isAuthenticated, loading: authLoading } = useAuth()
  const [filter, setFilter] = useState('all')
  const [conversations, setConversations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [archivingId, setArchivingId] = useState(null)

  const load = useCallback(
    async ({ quiet = false } = {}) => {
      if (!isAuthenticated) return
      if (!quiet) setLoading(true)
      try {
        const selected = FILTERS.find((item) => item.key === filter)
        const response = await messagingAPI.conversations(selected?.params)
        setConversations(response.data || [])
        setError('')
      } catch (err) {
        if (!quiet) setError(apiErrorMessage(err, t('loadError')))
      } finally {
        if (!quiet) setLoading(false)
      }
    },
    [filter, isAuthenticated, t]
  )

  useEffect(() => {
    if (authLoading) return
    if (!isAuthenticated) {
      setLoading(false)
      return
    }
    load()
  }, [authLoading, isAuthenticated, load])

  useEffect(() => {
    if (!isAuthenticated) return undefined
    const timer = setInterval(() => load({ quiet: true }), 30000)
    return () => clearInterval(timer)
  }, [isAuthenticated, load])

  const toggleArchive = async (conversation) => {
    setArchivingId(conversation.id)
    try {
      await messagingAPI.archive(conversation.id, !conversation.is_archived)
      await load({ quiet: true })
    } catch {
      // A failed archive is not worth a full-page error; the row stays put.
    } finally {
      setArchivingId(null)
    }
  }

  if (authLoading || (loading && conversations.length === 0)) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <MessageSquare className="mx-auto mb-4 h-12 w-12 text-gray-400" />
        <h1 className="mb-2 text-2xl font-bold">{t('inboxTitle')}</h1>
        <p className="mb-6 text-gray-600">{t('loginToSeeInbox')}</p>
        <Link href="/login" className="btn-primary">
          {t('login')}
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-gray-900">
            <Inbox className="h-7 w-7 text-primary" />
            {t('inboxTitle')}
          </h1>
          <p className="mt-1 text-sm text-gray-500">{t('inboxSubtitle')}</p>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-green-50 px-3 py-2 text-xs text-green-800">
          <ShieldCheck className="h-4 w-4" />
          {t('inboxSafety')}
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2 border-b border-gray-200 pb-3">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setFilter(item.key)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              filter === item.key
                ? 'bg-primary text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {t(`filters.${item.key}`)}
          </button>
        ))}
      </div>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
          <p className="mb-3 text-sm text-red-800">{error}</p>
          <button
            type="button"
            onClick={() => load()}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white"
          >
            {t('retry')}
          </button>
        </div>
      ) : conversations.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-12 text-center">
          <MessageSquare className="mx-auto mb-3 h-10 w-10 text-gray-400" />
          <p className="font-medium text-gray-800">{t('emptyInbox')}</p>
          <p className="mt-1 text-sm text-gray-500">{t('emptyInboxHint')}</p>
          <Link
            href="/products"
            className="mt-5 inline-block text-sm font-semibold text-primary hover:text-secondary"
          >
            {t('browseListings')}
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {conversations.map((conversation) => {
            const unread = conversation.unread_count || 0
            return (
              <li key={conversation.id}>
                <div className="flex items-stretch gap-1 rounded-2xl border border-gray-200 bg-white transition-shadow hover:shadow-md">
                  <Link
                    href={`/messages/${conversation.id}`}
                    className="flex min-w-0 flex-1 items-center gap-3 p-4"
                  >
                    <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded-xl bg-gray-100">
                      {conversation.listing?.primary_image ? (
                        <SafeImage
                          src={conversation.listing.primary_image}
                          alt=""
                          fill
                          sizes="56px"
                          className="object-cover"
                        />
                      ) : (
                        <MessageSquare className="absolute inset-0 m-auto h-6 w-6 text-gray-400" />
                      )}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3">
                        <p className="truncate font-semibold text-gray-900">
                          {conversation.other_user?.name ||
                            conversation.listing?.name}
                        </p>
                        <span className="shrink-0 text-xs text-gray-400">
                          {formatTimestamp(
                            conversation.last_message_at,
                            locale
                          )}
                        </span>
                      </div>
                      <p className="truncate text-sm text-gray-500">
                        {conversation.listing?.name}
                      </p>
                      <p
                        className={`truncate text-sm ${
                          unread > 0
                            ? 'font-semibold text-gray-900'
                            : 'text-gray-600'
                        }`}
                      >
                        {messagePreview(
                          conversation.last_message,
                          t,
                          conversation.listing?.currency
                        )}
                      </p>
                    </div>

                    {unread > 0 && (
                      <span className="ms-2 flex h-6 min-w-6 shrink-0 items-center justify-center rounded-full bg-primary px-1.5 text-xs font-bold text-white">
                        {unread > 99 ? '99+' : unread}
                      </span>
                    )}
                  </Link>

                  <button
                    type="button"
                    onClick={() => toggleArchive(conversation)}
                    disabled={archivingId === conversation.id}
                    className="my-3 me-3 flex h-9 w-9 items-center justify-center self-center rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-50"
                    title={
                      conversation.is_archived ? t('unarchive') : t('archive')
                    }
                    aria-label={
                      conversation.is_archived ? t('unarchive') : t('archive')
                    }
                  >
                    {archivingId === conversation.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : conversation.is_archived ? (
                      <ArchiveRestore className="h-4 w-4" />
                    ) : (
                      <Archive className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
