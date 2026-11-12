import { describe, expect, it } from 'vitest'

import {
  formatTimestamp,
  mergeMessages,
  messagePreview,
  offerActionsFor,
  responseTimeText,
  safetyFlagKeys,
} from './messaging'

const t = (key, values = {}) => {
  if (key === 'offerPreview') return `Offer ${values.amount} ${values.currency}`
  if (key === 'photoPreview') return 'Photo'
  if (key === 'noMessagesYet') return 'No messages yet'
  if (key === 'offerPreviewShort') return 'Offer'
  if (key === 'responseWithinMinutes') return `${values.count} min`
  if (key === 'responseWithinHours') return `${values.count} h`
  if (key === 'responseWithinDays') return `${values.count} d`
  return key
}

describe('mergeMessages', () => {
  it('deduplicates by id and keeps the newest server state', () => {
    const current = [
      { id: 1, body: 'one', is_read: false },
      { id: 2, body: 'two', is_read: false },
    ]
    const incoming = [
      { id: 2, body: 'two', is_read: true },
      { id: 3, body: 'three', is_read: false },
    ]

    expect(mergeMessages(current, incoming)).toEqual([
      { id: 1, body: 'one', is_read: false },
      { id: 2, body: 'two', is_read: true },
      { id: 3, body: 'three', is_read: false },
    ])
  })

  it('tolerates empty poll results', () => {
    expect(mergeMessages([{ id: 1 }], [])).toEqual([{ id: 1 }])
    expect(mergeMessages(undefined, [{ id: 1 }])).toEqual([{ id: 1 }])
  })
})

describe('messagePreview', () => {
  it('renders text, photos and offers differently', () => {
    expect(messagePreview({ kind: 'TEXT', body: 'Hello' }, t)).toBe('Hello')
    expect(messagePreview({ kind: 'IMAGE' }, t)).toBe('Photo')
    expect(messagePreview({ kind: 'OFFER', offer_amount: '45000' }, t)).toBe(
      'Offer 45,000 DZD'
    )
    expect(messagePreview(null, t)).toBe('No messages yet')
  })
})

describe('responseTimeText', () => {
  it('formats minutes, hours and days', () => {
    expect(responseTimeText(30, t)).toBe('30 min')
    expect(responseTimeText(120, t)).toBe('2 h')
    expect(responseTimeText(2880, t)).toBe('2 d')
  })

  it('hides a badge with no usable samples', () => {
    expect(responseTimeText(null, t)).toBeNull()
    expect(responseTimeText(0, t)).toBeNull()
    expect(responseTimeText('nope', t)).toBeNull()
  })
})

describe('offerActionsFor', () => {
  it('lets only the recipient respond to a pending offer', () => {
    const offer = { status: 'PENDING', created_by: 7 }

    expect(offerActionsFor(offer, 7)).toEqual(['withdraw'])
    expect(offerActionsFor(offer, 8)).toEqual(['accept', 'decline', 'counter'])
  })

  it('offers no action once the offer is resolved', () => {
    expect(offerActionsFor({ status: 'ACCEPTED', created_by: 7 }, 8)).toEqual(
      []
    )
  })
})

describe('safetyFlagKeys', () => {
  it('keeps known flags once and drops unknown values', () => {
    expect(
      safetyFlagKeys([
        'phone_number',
        'phone_number',
        'unknown',
        'off_platform_payment',
      ])
    ).toEqual(['phone_number', 'off_platform_payment'])
    expect(safetyFlagKeys(null)).toEqual([])
  })
})

describe('formatTimestamp', () => {
  it('formats a date and tolerates an empty value', () => {
    expect(formatTimestamp('2026-01-02T10:30:00Z', 'en')).not.toBe('')
    expect(formatTimestamp(null, 'fr')).toBe('')
    expect(formatTimestamp('not-a-date', 'ar')).toBe('')
  })
})
