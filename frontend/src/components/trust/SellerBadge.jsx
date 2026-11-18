'use client'

import { Phone, ShieldCheck, Store } from 'lucide-react'
import { useTranslations } from 'next-intl'

const ICONS = {
  STORE: Store,
  ID: ShieldCheck,
  PHONE: Phone,
  UNVERIFIED: null,
}

/**
 * Seller tier badges (Phase 17).
 *
 * The tier is derived server-side from *approved* verification rows, never
 * from a client-supplied flag. A badge is a signal, not a guarantee - the
 * safety centre says so in plain language, and the tooltip repeats it.
 */
export default function SellerBadge({
  badges,
  tier,
  className = '',
  showUnverified = false,
}) {
  const t = useTranslations('trust.badges')

  const rows = badges && badges.length ? badges : tier ? [{ code: tier }] : []

  const visible = rows.filter(
    (row) => showUnverified || row.code !== 'UNVERIFIED'
  )

  if (!visible.length) return null

  return (
    <span className={`inline-flex flex-wrap items-center gap-1 ${className}`}>
      {visible.map((row) => {
        if (!(row.code in ICONS)) return null
        const Icon = ICONS[row.code]
        return (
          <span
            key={row.code}
            title={t('tooltip')}
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
              row.code === 'STORE'
                ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
                : row.code === 'ID'
                  ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-200'
                  : 'bg-gray-100 text-gray-700 ring-1 ring-gray-200'
            }`}
          >
            {Icon && <Icon className="h-3 w-3" />}
            {t(row.code)}
          </span>
        )
      })}
    </span>
  )
}
