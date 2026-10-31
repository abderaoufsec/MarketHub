import { Inter, Noto_Sans_Arabic } from 'next/font/google'
import { cookies } from 'next/headers'
import { NextIntlClientProvider } from 'next-intl'
import './globals.css'
import { AuthProvider } from '../context/AuthContext'
import Header from '../components/common/Header'
import Footer from '../components/common/Footer'
import ToastProvider from '../components/common/Toaster'
// Validates NEXT_PUBLIC_* configuration at boot (fails fast if it is missing).
import { SITE_NAME } from '../lib/env'
import { LOCALE_COOKIE, dirFor, resolveLocale } from '../i18n/config'
import en from '../i18n/messages/en.json'
import fr from '../i18n/messages/fr.json'
import ar from '../i18n/messages/ar.json'

// Both families load as CSS variables rather than applied classes: the body
// font must switch with `<html lang>` without a per-element class change. The
// Latin stack comes first — `Noto Sans Arabic` covers Latin too, so the French
// and English UIs render in Inter and Arabic falls through to Noto on the
// Arabic glyphs (Phase 11: "Arabic-friendly font stack with a fallback").
const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })
const notoArabic = Noto_Sans_Arabic({
  subsets: ['arabic'],
  variable: '--font-noto-arabic',
})

const MESSAGES = { en, fr, ar }

export const metadata = {
  title: `${SITE_NAME} - Your Online Marketplace`,
  description:
    'Connect sellers and buyers through a simple, secure online marketplace',
  // Phase 14: the public/ assets that make the site installable and
  // shareable. `favicon.ico` is served from public/ automatically; naming it
  // here pins the other sizes for browsers and iOS.
  manifest: '/manifest.webmanifest',
  icons: {
    icon: [
      { url: '/favicon-32.png', sizes: '32x32', type: 'image/png' },
      { url: '/favicon-16.png', sizes: '16x16', type: 'image/png' },
    ],
    apple: '/apple-touch-icon.png',
  },
}

export const viewport = {
  themeColor: '#007BFF',
}

export default function RootLayout({ children }) {
  // Phase 11 (docs/todo.md): locale lives in a cookie — no `/<lang>/` URL
  // segment until Phase 26's SEO work. Read server-side so `<html lang dir>`
  // and the messages are correct in the first byte; no client-side flash.
  const locale = resolveLocale(cookies().get(LOCALE_COOKIE)?.value)

  return (
    <html lang={locale} dir={dirFor(locale)} className="scroll-smooth">
      <body className={`${inter.variable} ${notoArabic.variable} font-sans`}>
        <NextIntlClientProvider
          locale={locale}
          messages={MESSAGES[locale]}
          timeZone="Africa/Algiers"
        >
          <AuthProvider>
            <div className="flex flex-col min-h-screen">
              <Header />
              <main className="flex-grow bg-gray-50">{children}</main>
              <Footer />
            </div>
            <ToastProvider />
          </AuthProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
