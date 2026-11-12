/**
 * Pure helpers for the Phase 16 inbox and chat.
 *
 * Keeping the polling merge, previews and offer permissions here means the
 * pages stay render-focused and the rules get unit tests that do not need a
 * browser or a live API.
 */

/** Merge a poll result into the thread without duplicating messages. */
export function mergeMessages(current, incoming) {
  const byId = new Map((current || []).map((message) => [message.id, message]))
  for (const message of incoming || []) {
    // A later poll carries fresher `is_read`/`read_at`, so the incoming row wins.
    byId.set(message.id, message)
  }
  return [...byId.values()].sort((a, b) => a.id - b.id)
}

/** One-line inbox preview for text, photo and offer messages. */
export function messagePreview(message, t, currency = 'DZD') {
  if (!message) return t('noMessagesYet')
  if (message.kind === 'OFFER') {
    return message.offer_amount
      ? t('offerPreview', {
          amount: Number(message.offer_amount).toLocaleString(),
          currency,
        })
      : t('offerPreviewShort')
  }
  if (message.kind === 'IMAGE') return t('photoPreview')
  return message.body || t('noMessagesYet')
}

/** Human response-time badge; `null` when the seller has too few samples. */
export function responseTimeText(minutes, t) {
  const value = Number(minutes)
  if (!Number.isFinite(value) || value <= 0) return null
  if (value < 60)
    return t('responseWithinMinutes', { count: Math.round(value) })
  if (value < 1440) {
    return t('responseWithinHours', {
      count: Math.max(1, Math.round(value / 60)),
    })
  }
  return t('responseWithinDays', {
    count: Math.max(1, Math.round(value / 1440)),
  })
}

/** Which offer buttons the viewer may use. Empty for a resolved offer. */
export function offerActionsFor(offer, userId) {
  if (!offer || offer.status !== 'PENDING') return []
  if (offer.created_by === userId) return ['withdraw']
  return ['accept', 'decline', 'counter']
}

/** Short timestamp for inbox rows and bubbles (Western digits in Arabic). */
export function formatTimestamp(value, locale = 'en') {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(locale === 'ar' ? 'ar-DZ' : locale, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

/** Stable reasons returned by `apps.messaging.spam.safety_flags`. */
export function safetyFlagKeys(flags) {
  return [...new Set(flags || [])].filter((flag) =>
    ['phone_number', 'suspicious_link', 'off_platform_payment'].includes(flag)
  )
}
