'use client'

import { useEffect, useState } from 'react'
import { Flag, X } from 'lucide-react'
import { useTranslations } from 'next-intl'

const REASONS = ['SPAM', 'SCAM', 'HARASSMENT', 'PROHIBITED_ITEM', 'OTHER']

/**
 * Abuse report dialog (Phase 16).
 *
 * The parent decides *what* is reported (message/conversation/user) and the
 * server derives the reported person; this dialog only collects the reason
 * and a short explanation.
 */
export default function ReportModal({
  isOpen,
  onClose,
  onSubmit,
  busy = false,
}) {
  const t = useTranslations('messages')
  const [reason, setReason] = useState('SPAM')
  const [details, setDetails] = useState('')

  useEffect(() => {
    if (!isOpen) return
    setReason('SPAM')
    setDetails('')
  }, [isOpen])

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="report-dialog-title"
    >
      <form
        onSubmit={(event) => {
          event.preventDefault()
          onSubmit({ reason, details: details.trim() })
        }}
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-red-50 p-2 text-red-600">
              <Flag className="h-5 w-5" />
            </span>
            <h2 id="report-dialog-title" className="text-lg font-semibold">
              {t('reportTitle')}
            </h2>
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

        <p className="mb-4 text-sm text-gray-600">{t('reportIntro')}</p>

        <label className="mb-1 block text-sm font-medium text-gray-700">
          {t('reportReason')}
        </label>
        <select
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          className="mb-4 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-primary focus:ring-primary"
        >
          {REASONS.map((value) => (
            <option key={value} value={value}>
              {t(`reportReasons.${value}`)}
            </option>
          ))}
        </select>

        <label className="mb-1 block text-sm font-medium text-gray-700">
          {t('reportDetails')}
        </label>
        <textarea
          rows={4}
          maxLength={2000}
          value={details}
          onChange={(event) => setDetails(event.target.value)}
          className="mb-5 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-primary focus:ring-primary"
          placeholder={t('reportDetailsPlaceholder')}
        />

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
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? t('sending') : t('submitReport')}
          </button>
        </div>
      </form>
    </div>
  )
}
