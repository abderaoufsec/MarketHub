'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import {
  ArrowLeft,
  BadgeDollarSign,
  Flag,
  ImagePlus,
  Loader2,
  Lock,
  Send,
  ShieldAlert,
  ShieldCheck,
  UserX,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useTranslations } from 'next-intl'
import { mediaAPI, messagingAPI } from '../../../lib/api'
import { apiErrorMessage } from '../../../lib/errors'
import { useAuth } from '../../../context/AuthContext'
import { mergeMessages } from '../../../lib/messaging'
import MessageBubble from '../../../components/messaging/MessageBubble'
import OfferModal from '../../../components/messaging/OfferModal'
import ReportModal from '../../../components/messaging/ReportModal'
import SafeImage from '../../../components/common/SafeImage'
import { compressImage, isSupportedImage } from '../../../lib/imageCompression'

const POLL_MS = 5000

/**
 * One listing conversation (Phase 16).
 *
 * The MVP transport is polling: the server already exposes the thread as an
 * id-ordered list, so every poll merges by id and read receipts are a
 * conversation-level watermark. Offers are messages, which means accept,
 * counter and withdraw happen inline in the transcript instead of on a
 * separate negotiation page.
 */
export default function ChatPage() {
  const t = useTranslations('messages')
  const params = useParams()
  const router = useRouter()
  const conversationId = Number(params.id)
  const { user, isAuthenticated, loading: authLoading } = useAuth()

  const [conversation, setConversation] = useState(null)
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [offerOpen, setOfferOpen] = useState(false)
  const [offerBusy, setOfferBusy] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)
  const [reportTarget, setReportTarget] = useState(null)
  const [reportBusy, setReportBusy] = useState(false)
  const [blockBusy, setBlockBusy] = useState(false)

  const bottomRef = useRef(null)
  const fileInputRef = useRef(null)
  const lastReadIdRef = useRef(0)

  const scrollToBottom = useCallback((behavior = 'smooth') => {
    bottomRef.current?.scrollIntoView({ behavior, block: 'end' })
  }, [])

  const loadConversation = useCallback(async () => {
    const response = await messagingAPI.conversation(conversationId)
    setConversation(response.data)
    return response.data
  }, [conversationId])

  const markRead = useCallback(
    async (rows) => {
      const incoming = rows.filter((message) => message.sender?.id !== user?.id)
      const newest = incoming.reduce(
        (max, message) => Math.max(max, message.id),
        0
      )
      if (newest <= lastReadIdRef.current) return
      try {
        const response = await messagingAPI.markRead(conversationId)
        lastReadIdRef.current = newest
        setConversation(response.data)
      } catch {
        // A read receipt is best-effort; the next poll tries again.
      }
    },
    [conversationId, user?.id]
  )

  const loadMessages = useCallback(
    async ({ quiet = false } = {}) => {
      try {
        const response = await messagingAPI.messages(conversationId)
        const rows = response.data?.results || []
        setMessages((current) => mergeMessages(current, rows))
        if (!quiet) setError('')
        await markRead(rows)
      } catch (err) {
        if (!quiet) setError(apiErrorMessage(err, t('loadConversationError')))
      }
    },
    [conversationId, markRead, t]
  )

  useEffect(() => {
    if (authLoading) return
    if (!isAuthenticated) {
      setLoading(false)
      return
    }
    if (!Number.isFinite(conversationId) || conversationId <= 0) {
      setError(t('conversationNotFound'))
      setLoading(false)
      return
    }
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const [record] = await Promise.all([loadConversation(), loadMessages()])
        if (!cancelled && record) {
          setTimeout(() => scrollToBottom('auto'), 0)
        }
      } catch (err) {
        if (!cancelled) {
          setError(apiErrorMessage(err, t('loadConversationError')))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [
    authLoading,
    conversationId,
    isAuthenticated,
    loadConversation,
    loadMessages,
    scrollToBottom,
    t,
  ])

  useEffect(() => {
    if (!isAuthenticated || !conversation || conversation.is_blocked) {
      return undefined
    }
    const timer = setInterval(async () => {
      if (typeof document !== 'undefined' && document.hidden) return
      try {
        const response = await messagingAPI.messages(conversationId)
        const rows = response.data?.results || []
        setMessages((current) => mergeMessages(current, rows))
        await markRead(rows)
      } catch {
        // Polling failures are expected on a flaky connection; keep the last
        // good transcript and try again on the next tick.
      }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [conversation, conversationId, isAuthenticated, markRead])

  useEffect(() => {
    scrollToBottom()
  }, [messages.length, scrollToBottom])

  const handleSend = async (event) => {
    event?.preventDefault()
    const body = draft.trim()
    if (!body || sending || conversation?.is_blocked) return
    setSending(true)
    try {
      const response = await messagingAPI.sendMessage(conversationId, { body })
      setMessages((current) => mergeMessages(current, [response.data]))
      // Only clear what was actually sent: a fast typer may already have
      // started the next message while this request was in flight.
      setDraft((current) => (current.trim() === body ? '' : current))
      const refreshed = await loadConversation()
      setConversation(refreshed)
      setTimeout(() => scrollToBottom(), 0)
    } catch (err) {
      toast.error(apiErrorMessage(err, t('sendError')))
    } finally {
      setSending(false)
    }
  }

  const handleImage = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || uploading) return
    if (!isSupportedImage(file)) {
      toast.error(t('imageTypeError'))
      return
    }
    setUploading(true)
    try {
      const compressed = await compressImage(file)
      const uploaded = await mediaAPI.upload(compressed)
      const response = await messagingAPI.sendMessage(conversationId, {
        image_id: uploaded.data.id,
      })
      setMessages((current) => mergeMessages(current, [response.data]))
      const refreshed = await loadConversation()
      setConversation(refreshed)
      setTimeout(() => scrollToBottom(), 0)
    } catch (err) {
      toast.error(apiErrorMessage(err, t('imageUploadError')))
    } finally {
      setUploading(false)
    }
  }

  const handleOffer = async ({ amount, note }) => {
    setOfferBusy(true)
    try {
      const response = await messagingAPI.createOffer(conversationId, {
        amount,
        note,
      })
      setMessages((current) => mergeMessages(current, [response.data.message]))
      setOfferOpen(false)
      await loadConversation()
      toast.success(t('offerSent'))
      setTimeout(() => scrollToBottom(), 0)
    } catch (err) {
      toast.error(apiErrorMessage(err, t('offerError')))
    } finally {
      setOfferBusy(false)
    }
  }

  const handleOfferAction = async (offerId, action, data = {}) => {
    try {
      await messagingAPI.offerAction(offerId, action, data)
      await loadMessages({ quiet: true })
      await loadConversation()
      toast.success(t(`offerDone.${action}`))
      return true
    } catch (err) {
      toast.error(apiErrorMessage(err, t('offerActionError')))
      return false
    }
  }

  const openReport = (message = null) => {
    setReportTarget(
      message ? { message_id: message.id } : { conversation_id: conversationId }
    )
    setReportOpen(true)
  }

  const submitReport = async ({ reason, details }) => {
    setReportBusy(true)
    try {
      await messagingAPI.report({
        ...(reportTarget || {}),
        reason,
        details,
      })
      setReportOpen(false)
      toast.success(t('reportSent'))
    } catch (err) {
      toast.error(apiErrorMessage(err, t('reportError')))
    } finally {
      setReportBusy(false)
    }
  }

  const toggleBlock = async () => {
    const otherId = conversation?.other_user?.id
    if (!otherId) return
    const nextBlocked = !conversation.is_blocked
    if (
      nextBlocked &&
      typeof window !== 'undefined' &&
      !window.confirm(
        t('blockConfirm', { name: conversation.other_user?.name || '' })
      )
    ) {
      return
    }
    setBlockBusy(true)
    try {
      if (nextBlocked) {
        await messagingAPI.blockUser(otherId)
        toast.success(t('blockedToast'))
      } else {
        await messagingAPI.unblockUser(otherId)
        toast.success(t('unblockedToast'))
      }
      await loadConversation()
    } catch (err) {
      toast.error(apiErrorMessage(err, t('blockError')))
    } finally {
      setBlockBusy(false)
    }
  }

  if (authLoading || loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <Lock className="mx-auto mb-4 h-12 w-12 text-gray-400" />
        <h1 className="mb-2 text-2xl font-bold">{t('inboxTitle')}</h1>
        <p className="mb-6 text-gray-600">{t('loginToSeeInbox')}</p>
        <button
          type="button"
          onClick={() => router.push('/login')}
          className="btn-primary"
        >
          {t('login')}
        </button>
      </div>
    )
  }

  if (error && !conversation) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <ShieldAlert className="mx-auto mb-4 h-12 w-12 text-red-400" />
        <p className="mb-5 text-gray-700">{error}</p>
        <Link href="/messages" className="btn-primary">
          {t('backToInbox')}
        </Link>
      </div>
    )
  }

  if (!conversation) return null

  const listing = conversation.listing
  const other = conversation.other_user
  const canOffer = listing?.price_mode === 'NEGOTIABLE' && conversation.can_send
  const listingHref = listing?.canonical_path || `/products/${listing?.id}`

  return (
    <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-4xl flex-col bg-gray-50">
      <div className="border-b border-gray-200 bg-white px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <Link
            href="/messages"
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100"
            aria-label={t('backToInbox')}
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div className="h-10 w-10 shrink-0 overflow-hidden rounded-full bg-gray-100">
            {listing?.primary_image ? (
              <SafeImage
                src={listing.primary_image}
                alt=""
                width={40}
                height={40}
                className="h-10 w-10 object-cover"
              />
            ) : (
              <UserX className="m-2 h-6 w-6 text-gray-400" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold text-gray-900">
              {other?.name || listing?.name}
            </p>
            <Link
              href={listingHref}
              className="truncate text-sm text-gray-500 hover:text-primary"
            >
              {listing?.name}
            </Link>
          </div>
          <div className="flex items-center gap-1">
            {canOffer && (
              <button
                type="button"
                onClick={() => setOfferOpen(true)}
                className="rounded-lg p-2 text-primary hover:bg-primary/10"
                title={t('makeOffer')}
                aria-label={t('makeOffer')}
              >
                <BadgeDollarSign className="h-5 w-5" />
              </button>
            )}
            <button
              type="button"
              onClick={() => openReport()}
              className="rounded-lg p-2 text-gray-500 hover:bg-gray-100"
              title={t('reportConversation')}
              aria-label={t('reportConversation')}
            >
              <Flag className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={toggleBlock}
              disabled={blockBusy}
              className={`rounded-lg p-2 disabled:opacity-50 ${
                conversation.is_blocked
                  ? 'text-gray-500 hover:bg-gray-100'
                  : 'text-red-600 hover:bg-red-50'
              }`}
              title={
                conversation.is_blocked ? t('unblockUser') : t('blockUser')
              }
              aria-label={
                conversation.is_blocked ? t('unblockUser') : t('blockUser')
              }
            >
              {blockBusy ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <UserX className="h-5 w-5" />
              )}
            </button>
          </div>
        </div>

        <div className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
          {t('safetyBanner')}
        </div>

        {conversation.is_blocked && (
          <p className="mt-2 rounded-lg bg-gray-100 px-3 py-2 text-sm text-gray-700">
            {t('blockedBanner')}
          </p>
        )}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-5 sm:px-6">
        {messages.length === 0 && (
          <div className="mx-auto max-w-md rounded-xl border border-dashed border-gray-300 bg-white p-6 text-center text-sm text-gray-600">
            <p className="font-medium text-gray-800">{t('startTitle')}</p>
            <p className="mt-1">{t('startHint')}</p>
          </div>
        )}
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            currentUserId={user?.id}
            onOfferAction={handleOfferAction}
            onReport={openReport}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSend}
        className="sticky bottom-0 border-t border-gray-200 bg-white px-4 py-3 sm:px-6"
      >
        <div className="flex items-end gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            onChange={handleImage}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || conversation.is_blocked}
            className="rounded-lg p-2.5 text-gray-500 hover:bg-gray-100 disabled:opacity-40"
            title={t('attachPhoto')}
            aria-label={t('attachPhoto')}
          >
            {uploading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <ImagePlus className="h-5 w-5" />
            )}
          </button>
          <textarea
            rows={1}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                handleSend(event)
              }
            }}
            disabled={conversation.is_blocked}
            maxLength={2000}
            placeholder={
              conversation.is_blocked
                ? t('blockedComposer')
                : t('messagePlaceholder')
            }
            className="max-h-32 min-h-[44px] flex-1 resize-y rounded-xl border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-primary disabled:bg-gray-100"
          />
          <button
            type="submit"
            disabled={!draft.trim() || sending || conversation.is_blocked}
            className="btn-primary flex h-11 w-11 items-center justify-center rounded-xl p-0 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label={t('send')}
          >
            {sending ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <Send className="h-5 w-5" />
            )}
          </button>
        </div>
        <p className="mt-1 text-[11px] text-gray-400">
          {t('firstMessageHint')}
        </p>
      </form>

      <OfferModal
        isOpen={offerOpen}
        onClose={() => setOfferOpen(false)}
        onSubmit={handleOffer}
        listingName={listing?.name}
        currency={listing?.currency || 'DZD'}
        busy={offerBusy}
      />
      <ReportModal
        isOpen={reportOpen}
        onClose={() => setReportOpen(false)}
        onSubmit={submitReport}
        busy={reportBusy}
      />
    </div>
  )
}
