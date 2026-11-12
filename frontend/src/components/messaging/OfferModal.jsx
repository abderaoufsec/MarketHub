'use client'

import { useEffect, useState } from 'react'
import { X, BadgeDollarSign } from 'lucide-react'
import { useTranslations } from 'next-intl'

/**
 * Make-an-offer dialog (Phase 16).
 *
 * The amount is deliberately a plain number: currency formatting belongs to
 * the listing, and the server validates the value again inside the one-open-
 * offer transaction. The parent owns the API call so the same dialog can be
 * reused from a listing or from the chat.
 */
export default function OfferModal({
  isOpen,
  onClose,
  onSubmit,
  listingName,
  currency = 'DZD',
  busy = false,
}) {
  const t = useTranslations('messages')
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isOpen) return
    setAmount('')
    setNote('')
    setError('')
  }, [isOpen])

  if (!isOpen) return null

  const handleSubmit = (event) => {
    event.preventDefault()
    const numeric = Number(amount)
    if (!Number.isFinite(numeric) || numeric < 1) {
      setError(t('offerAmountInvalid'))
      return
    }
    setError('')
    onSubmit({ amount: numeric.toFixed(2), note: note.trim() })
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="offer-dialog-title"
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-primary/10 p-2 text-primary">
              <BadgeDollarSign className="h-5 w-5" />
            </span>
            <div>
              <h2 id="offer-dialog-title" className="text-lg font-semibold">
                {t('makeOffer')}
              </h2>
              {listingName && (
                <p className="line-clamp-1 text-sm text-gray-500">
                  {listingName}
                </p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-gray-500 hover:bg-gray-100"
            aria-label={t('close')}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <label
          htmlFor="offer-amount"
          className="mb-1 block text-sm font-medium text-gray-700"
        >
          {t('offerAmount', { currency })}
        </label>
        <input
          id="offer-amount"
          type="number"
          min="1"
          step="1"
          inputMode="decimal"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          className="mb-1 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-primary focus:ring-primary"
          placeholder={t('offerAmountPlaceholder')}
          autoFocus
        />
        {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

        <label
          htmlFor="offer-note"
          className="mb-1 mt-4 block text-sm font-medium text-gray-700"
        >
          {t('offerNote')}
        </label>
        <textarea
          id="offer-note"
          rows={3}
          maxLength={2000}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          className="mb-2 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-primary focus:ring-primary"
          placeholder={t('offerNotePlaceholder')}
        />
        <p className="mb-5 text-xs text-gray-500">{t('offerSafety')}</p>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            {t('cancel')}
          </button>
          <button
            type="submit"
            disabled={busy}
            className="btn-primary disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? t('sending') : t('sendOffer')}
          </button>
        </div>
      </form>
    </div>
  )
}
