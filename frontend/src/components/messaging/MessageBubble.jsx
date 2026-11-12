'use client'

import { useState } from 'react'
import { Check, CheckCheck, Flag, ShieldAlert } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import SafeImage from '../common/SafeImage'
import { usePrice } from '../../lib/currency'
import {
  formatTimestamp,
  offerActionsFor,
  safetyFlagKeys,
} from '../../lib/messaging'

/**
 * One chat row (Phase 16).
 *
 * Offers live in the transcript rather than a separate screen: accepting,
 * countering or withdrawing happens exactly where the negotiation happened.
 * `offerActionsFor` mirrors the server's rule (only the recipient responds;
 * only the creator withdraws), so the UI never offers a 403.
 */
export default function MessageBubble({
  message,
  currentUserId,
  onOfferAction,
  onReport,
}) {
  const t = useTranslations('messages')
  const locale = useLocale()
  const price = usePrice()
  const [counterOpen, setCounterOpen] = useState(false)
  const [counterAmount, setCounterAmount] = useState('')
  const [busy, setBusy] = useState(false)
  const own = message.sender?.id === currentUserId
  const flags = safetyFlagKeys(message.safety_flags)

  const runAction = async (action, data = {}) => {
    setBusy(true)
    try {
      const accepted = await onOfferAction?.(message.offer.id, action, data)
      if (accepted !== false) setCounterOpen(false)
    } finally {
      setBusy(false)
    }
  }

  const submitCounter = async (event) => {
    event.preventDefault()
    const amount = Number(counterAmount)
    if (!Number.isFinite(amount) || amount < 1) return
    await runAction('counter', { amount: amount.toFixed(2) })
  }

  return (
    <div className={`flex ${own ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm shadow-sm ${
          own
            ? 'rounded-br-sm bg-primary text-white'
            : 'rounded-bl-sm border border-gray-200 bg-white text-gray-800'
        }`}
      >
        {!own && (
          <p className="mb-1 text-xs font-semibold text-gray-600">
            {message.sender?.name}
          </p>
        )}

        {message.kind === 'OFFER' && message.offer ? (
          <div
            className={`my-1 min-w-[220px] rounded-xl border p-3 ${
              own
                ? 'border-white/30 bg-white/10'
                : 'border-primary/20 bg-primary/5'
            }`}
          >
            <p className="text-xs uppercase tracking-wide opacity-75">
              {t('priceOffer')}
            </p>
            <p className="mt-1 text-xl font-bold">
              {price(message.offer.amount)}
            </p>
            <p className="mt-1 text-xs opacity-80">
              {t(`offerStatus.${message.offer.status}`)}
            </p>

            {message.offer.status === 'PENDING' &&
              offerActionsFor(message.offer, currentUserId).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {offerActionsFor(message.offer, currentUserId).map(
                    (action) =>
                      action !== 'counter' && (
                        <button
                          key={action}
                          type="button"
                          disabled={busy}
                          onClick={() => runAction(action)}
                          className={`rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50 ${
                            action === 'accept'
                              ? 'bg-green-600 text-white hover:bg-green-700'
                              : action === 'decline'
                                ? 'bg-gray-200 text-gray-800 hover:bg-gray-300'
                                : 'border border-red-300 text-red-700 hover:bg-red-50'
                          }`}
                        >
                          {t(`offerActions.${action}`)}
                        </button>
                      )
                  )}
                  {offerActionsFor(message.offer, currentUserId).includes(
                    'counter'
                  ) && (
                    <button
                      type="button"
                      onClick={() => setCounterOpen((value) => !value)}
                      className="rounded-lg border border-primary px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10"
                    >
                      {t('offerActions.counter')}
                    </button>
                  )}
                </div>
              )}

            {counterOpen && (
              <form onSubmit={submitCounter} className="mt-2 flex gap-2">
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={counterAmount}
                  onChange={(event) => setCounterAmount(event.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-2 py-1.5 text-gray-900"
                  placeholder={t('counterAmount')}
                  autoFocus
                />
                <button
                  type="submit"
                  disabled={busy}
                  className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {t('sendCounter')}
                </button>
              </form>
            )}
          </div>
        ) : (
          <>
            {message.image?.url && (
              <SafeImage
                src={message.image.url}
                alt={t('sharedPhoto')}
                width={320}
                height={240}
                className="mb-2 max-h-72 w-full rounded-xl object-cover"
              />
            )}
            {message.body && (
              <p className="whitespace-pre-wrap break-words">{message.body}</p>
            )}
          </>
        )}

        {flags.length > 0 && (
          <p
            className={`mt-2 flex items-start gap-1 text-xs ${
              own ? 'text-white/85' : 'text-amber-700'
            }`}
          >
            <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {t(`safety.${flags[0]}`)}
          </p>
        )}

        <div
          className={`mt-1 flex items-center justify-end gap-1 text-[11px] ${
            own ? 'text-white/75' : 'text-gray-400'
          }`}
        >
          <span>{formatTimestamp(message.created_at, locale)}</span>
          {own &&
            (message.is_read ? (
              <CheckCheck className="h-3.5 w-3.5" title={t('readReceipt')} />
            ) : (
              <Check className="h-3.5 w-3.5" title={t('sentReceipt')} />
            ))}
          {!own && onReport && (
            <button
              type="button"
              onClick={() => onReport(message)}
              className="ms-1 rounded p-0.5 hover:bg-gray-100 hover:text-gray-700"
              title={t('reportMessage')}
              aria-label={t('reportMessage')}
            >
              <Flag className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
