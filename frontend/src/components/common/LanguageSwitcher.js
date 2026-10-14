'use client'

import { useLocale, useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { Languages } from 'lucide-react'
import { LOCALES, LOCALE_COOKIE } from '../../i18n/config'
import {
  getPriceDisplay,
  setPriceDisplay,
  subscribePriceDisplay,
} from '../../lib/currency'

/**
 * Language + price-display preferences (Phase 11 of docs/todo.md).
 *
 * Switching writes the `mh_locale` cookie and calls `router.refresh()`: the
 * root layout re-reads the cookie server-side, so `<html lang dir>` and every
 * translated string update together — no reload, no half-translated page.
 * The price-display toggle notifies `usePrice`'s store directly, so prices
 * re-render instantly without a server round-trip.
 *
 * Native names on purpose ("العربية", not "Arabic"): that is how people find
 * their own language in a switcher.
 */
const LOCALE_NAMES = { fr: 'Français', ar: 'العربية', en: 'English' }

function PriceDisplayOption({ mode, current, onSelect }) {
  const t = useTranslations('common')
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={mode === current}
      onClick={() => onSelect(mode)}
      className={`block w-full text-start px-4 py-2 text-sm transition-colors ${
        mode === current
          ? 'text-primary font-semibold bg-primary-50'
          : 'text-gray-700 hover:bg-gray-50'
      }`}
    >
      {mode === 'standard'
        ? t('preferences.priceStandard')
        : t('preferences.priceMillions')}
    </button>
  )
}

export default function LanguageSwitcher() {
  const locale = useLocale()
  const t = useTranslations('common')
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [display, setDisplay] = useState('standard')
  const containerRef = useRef(null)

  // `standard` during hydration (server snapshot), then the cookie value —
  // the hydration-safe pattern described in src/lib/currency.js.
  useEffect(() => {
    setDisplay(getPriceDisplay())
    return subscribePriceDisplay(() => setDisplay(getPriceDisplay()))
  }, [])

  // Close on outside click.
  useEffect(() => {
    if (!open) return undefined
    const onClick = (event) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const selectLocale = (next) => {
    setOpen(false)
    if (next === locale) return
    document.cookie = `${LOCALE_COOKIE}=${encodeURIComponent(
      next
    )}; path=/; max-age=31536000; SameSite=Lax`
    router.refresh()
  }

  const selectDisplay = (next) => {
    setPriceDisplay(next)
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('preferences.title')}
        className="flex items-center gap-1 px-2 py-2 rounded-md text-gray-700 hover:text-primary hover:bg-gray-50 transition-colors"
      >
        <Languages className="h-5 w-5" aria-hidden="true" />
        <span className="hidden sm:inline text-sm font-medium">
          {LOCALE_NAMES[locale]}
        </span>
      </button>

      {open && (
        <div
          role="menu"
          aria-label={t('preferences.title')}
          className="absolute end-0 mt-2 w-56 bg-white rounded-lg shadow-xl py-2 border border-gray-100 z-50"
        >
          <div className="px-3 pb-1 text-xs font-semibold text-gray-400 uppercase tracking-wide">
            {t('preferences.language')}
          </div>
          {LOCALES.map((code) => (
            <button
              key={code}
              type="button"
              role="menuitemradio"
              aria-checked={code === locale}
              onClick={() => selectLocale(code)}
              className={`block w-full text-start px-4 py-2 text-sm transition-colors ${
                code === locale
                  ? 'text-primary font-semibold bg-primary-50'
                  : 'text-gray-700 hover:bg-gray-50'
              }`}
            >
              {LOCALE_NAMES[code]}
            </button>
          ))}

          <div className="border-t border-gray-100 my-1" />
          <div className="px-3 pb-1 pt-1 text-xs font-semibold text-gray-400 uppercase tracking-wide">
            {t('preferences.priceDisplay')}
          </div>
          <PriceDisplayOption
            mode="standard"
            current={display}
            onSelect={selectDisplay}
          />
          <PriceDisplayOption
            mode="millions"
            current={display}
            onSelect={selectDisplay}
          />
        </div>
      )}
    </div>
  )
}
