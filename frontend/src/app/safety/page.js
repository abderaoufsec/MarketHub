'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowRight, Flag, ShieldCheck } from 'lucide-react'
import { useTranslations } from 'next-intl'

import LoadingSpinner from '../../components/common/LoadingSpinner'
import { trustAPI } from '../../lib/api'

/**
 * Safety centre (Phase 17).
 *
 * The copy is authored server-side (`apps.trust.safety`) in fr/en/ar and
 * returned one language at a time, so the page has no long strings of its own
 * to keep in sync. Reports inside a listing still point here for guidance.
 */
export default function SafetyPage() {
  const t = useTranslations('trust.safety')
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    trustAPI
      .safetyCenter()
      .then((response) => {
        if (!cancelled) setPayload(response.data)
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
  }, [])

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <LoadingSpinner />
      </div>
    )
  }

  if (error || !payload) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center">
        <AlertTriangle className="mx-auto mb-4 h-10 w-10 text-amber-500" />
        <p className="text-gray-600">{t('error')}</p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
      <header className="mb-10">
        <span className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
          <ShieldCheck className="h-6 w-6" />
        </span>
        <h1 className="text-3xl font-bold text-gray-900">{payload.title}</h1>
        <p className="mt-3 max-w-2xl text-gray-600">{payload.intro}</p>
        <p className="mt-2 text-xs text-gray-400">
          {t('updated', { date: payload.updated_at })}
        </p>
      </header>

      <div className="grid gap-5 sm:grid-cols-2">
        {payload.sections.map((section) => (
          <section
            key={section.id}
            className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm"
          >
            <h2 className="mb-2 text-lg font-semibold text-gray-900">
              {section.title}
            </h2>
            <p className="mb-3 text-sm text-gray-600">{section.body}</p>
            <ul className="space-y-2 text-sm text-gray-600">
              {section.bullets.map((bullet) => (
                <li key={bullet} className="flex gap-2">
                  <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-500" />
                  <span>{bullet}</span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <div className="mt-10 flex flex-wrap gap-3">
        <Link
          href="/products"
          className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white hover:bg-primary-600"
        >
          <Flag className="h-4 w-4" />
          {t('reportCta')}
        </Link>
        <Link
          href="/profile/verification"
          className="inline-flex items-center gap-2 rounded-xl border border-gray-300 px-5 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50"
        >
          {t('verificationCta')}
          <ArrowRight className="h-4 w-4 rtl:rotate-180" />
        </Link>
      </div>
    </div>
  )
}
