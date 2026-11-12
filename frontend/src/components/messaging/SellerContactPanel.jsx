'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  BadgeDollarSign,
  Loader2,
  MessageCircle,
  MessageSquare,
  Phone,
  ShieldCheck,
  User,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useTranslations } from 'next-intl'
import { messagingAPI, productsAPI } from '../../lib/api'
import { apiErrorMessage } from '../../lib/errors'
import { useAuth } from '../../context/AuthContext'
import { responseTimeText } from '../../lib/messaging'
import OfferModal from './OfferModal'

/**
 * The contact / offer panel on a listing (Phase 16).
 *
 * The public payload only carries `phone_available`; clicking the reveal
 * button performs the authenticated, throttled, audited request and then
 * renders the server's ready-made `tel:`, `sms:` and WhatsApp links. Chat and
 * offers both start (or reuse) the same conversation, which is why one panel
 * owns the flow for both.
 */
export default function SellerContactPanel({ product }) {
  const t = useTranslations('products')
  const router = useRouter()
  const { user, isAuthenticated } = useAuth()
  const [busy, setBusy] = useState(false)
  const [revealed, setRevealed] = useState(null)
  const [offerOpen, setOfferOpen] = useState(false)
  const [offerBusy, setOfferBusy] = useState(false)

  if (!product) return null

  const isOwner = Boolean(user && product.seller?.id === user.id)
  const canOffer =
    product.price_mode === 'NEGOTIABLE' &&
    product.listing_type !== 'STORE_PRODUCT'
  const responseText = responseTimeText(
    product.seller?.response_time_minutes,
    t
  )

  const ensureSignedIn = () => {
    if (!isAuthenticated) {
      router.push('/login')
      return false
    }
    return true
  }

  const openConversation = async () => {
    if (!ensureSignedIn()) return null
    const response = await messagingAPI.startConversation(product.id)
    return response.data
  }

  const handleChat = async () => {
    setBusy(true)
    try {
      const conversation = await openConversation()
      if (conversation) router.push(`/messages/${conversation.id}`)
    } catch (error) {
      toast.error(apiErrorMessage(error, t('chatError')))
    } finally {
      setBusy(false)
    }
  }

  const handleReveal = async () => {
    if (!ensureSignedIn()) return
    setBusy(true)
    try {
      const response = await productsAPI.revealPhone(product.id)
      setRevealed(response.data)
      toast.success(t('phoneRevealed'))
    } catch (error) {
      toast.error(apiErrorMessage(error, t('revealError')))
    } finally {
      setBusy(false)
    }
  }

  const handleOffer = async ({ amount, note }) => {
    setOfferBusy(true)
    try {
      const conversation = await openConversation()
      if (!conversation) return
      await messagingAPI.createOffer(conversation.id, { amount, note })
      setOfferOpen(false)
      router.push(`/messages/${conversation.id}`)
    } catch (error) {
      toast.error(apiErrorMessage(error, t('offerError')))
    } finally {
      setOfferBusy(false)
    }
  }

  return (
    <div className="mb-6 rounded-xl border border-gray-200 bg-gray-50 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-lg font-semibold text-gray-900">
          <MessageSquare className="h-5 w-5 text-primary" />
          {t('contactSeller')}
        </h3>
        {responseText && (
          <span className="rounded-full bg-green-100 px-2.5 py-1 text-xs font-medium text-green-800">
            {responseText}
          </span>
        )}
      </div>

      <div className="mb-3 space-y-1 text-sm text-gray-700">
        {product.seller?.name && (
          <p className="flex items-center">
            <User className="me-2 h-4 w-4 text-gray-500" />
            {product.seller.name}
          </p>
        )}
        {product.wilaya_name && (
          <p className="text-gray-500">{product.wilaya_name}</p>
        )}
      </div>

      {isOwner ? (
        <p className="rounded-lg bg-white px-3 py-2 text-sm text-gray-600">
          {t('ownListing')}
        </p>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleChat}
              disabled={busy}
              className="btn-primary inline-flex items-center gap-2 disabled:opacity-60"
            >
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <MessageCircle className="h-4 w-4" />
              )}
              {t('chatWithSeller')}
            </button>

            {product.phone_available && !revealed && (
              <button
                type="button"
                onClick={handleReveal}
                disabled={busy}
                className="inline-flex items-center gap-2 rounded-lg border border-primary px-4 py-2 text-sm font-semibold text-primary hover:bg-primary/5 disabled:opacity-60"
              >
                <Phone className="h-4 w-4" />
                {t('revealPhone')}
              </button>
            )}

            {canOffer && (
              <button
                type="button"
                onClick={() => {
                  if (ensureSignedIn()) setOfferOpen(true)
                }}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-gray-800 hover:bg-gray-50"
              >
                <BadgeDollarSign className="h-4 w-4" />
                {t('makeOffer')}
              </button>
            )}
          </div>

          {revealed && (
            <div className="mt-3 rounded-lg border border-green-200 bg-white p-3">
              <p className="mb-2 text-sm font-semibold text-gray-900">
                {revealed.phone_number}
              </p>
              <div className="flex flex-wrap gap-2 text-sm">
                <a
                  href={revealed.call_url}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 font-medium text-white hover:bg-secondary"
                >
                  <Phone className="h-4 w-4" />
                  {t('call')}
                </a>
                <a
                  href={revealed.sms_url}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 font-medium text-gray-800 hover:bg-gray-50"
                >
                  <MessageSquare className="h-4 w-4" />
                  {t('sms')}
                </a>
                <a
                  href={revealed.whatsapp_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-green-600 px-3 py-1.5 font-medium text-white hover:bg-green-700"
                >
                  <MessageCircle className="h-4 w-4" />
                  {t('whatsapp')}
                </a>
              </div>
            </div>
          )}

          {!product.phone_available && !revealed && (
            <p className="mt-2 text-xs text-gray-500">{t('phoneChatOnly')}</p>
          )}

          <p className="mt-3 flex items-start gap-1.5 rounded-lg bg-amber-50 px-2.5 py-2 text-xs text-amber-800">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
            {t('contactSafety')}
          </p>
        </>
      )}

      <OfferModal
        isOpen={offerOpen}
        onClose={() => setOfferOpen(false)}
        onSubmit={handleOffer}
        listingName={product.name}
        currency={product.currency || 'DZD'}
        busy={offerBusy}
      />
    </div>
  )
}
