'use client'

import { useLocale } from 'next-intl'
import { Toaster } from 'react-hot-toast'
import { dirFor } from '../../i18n/config'

export default function ToastProvider() {
  // Phase 11: in RTL the toasts mirror to the top-left corner.
  const position = dirFor(useLocale()) === 'rtl' ? 'top-left' : 'top-right'

  return (
    <Toaster
      position={position}
      toastOptions={{
        duration: 4000,
        style: {
          background: '#363636',
          color: '#fff',
          borderRadius: '8px',
          padding: '16px',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
        },
        success: {
          iconTheme: {
            primary: '#10b981',
            secondary: '#fff',
          },
        },
        error: {
          iconTheme: {
            primary: '#ef4444',
            secondary: '#fff',
          },
        },
      }}
    />
  )
}
