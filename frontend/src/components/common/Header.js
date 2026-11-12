'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { useAuth } from '../../context/AuthContext'
import {
  ShoppingCart,
  User,
  Store,
  Menu,
  X,
  Heart,
  Plus,
  Search,
  MessageSquare,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { messagingAPI } from '../../lib/api'
import LanguageSwitcher from './LanguageSwitcher'

export default function Header() {
  const { user, isAuthenticated, isSeller, logout } = useAuth()
  const t = useTranslations('common')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)

  // Phase 16: the header badge polls the cheap aggregate endpoint. Chat
  // itself polls too; 30s here is enough to notice a new thread without
  // turning every page into a request loop.
  useEffect(() => {
    if (!isAuthenticated) {
      setUnreadCount(0)
      return undefined
    }
    let cancelled = false
    const refresh = async () => {
      try {
        const response = await messagingAPI.unreadCount()
        if (!cancelled) setUnreadCount(response.data?.unread_count || 0)
      } catch {
        // A transient failure must not break the navigation.
      }
    }
    refresh()
    const timer = setInterval(refresh, 30000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [isAuthenticated])

  const unreadBadge = (extra = '') =>
    unreadCount > 0 ? (
      <span
        className={`absolute -end-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white ${extra}`}
      >
        {unreadCount > 99 ? '99+' : unreadCount}
      </span>
    ) : null

  return (
    <motion.header
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="bg-white shadow-sm sticky top-0 z-50 backdrop-blur-sm bg-white/95"
    >
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2 group">
            <motion.div
              whileHover={{ rotate: [0, -10, 10, -10, 0] }}
              transition={{ duration: 0.5 }}
            >
              <Store className="h-8 w-8 text-primary group-hover:text-primary-600 transition-colors" />
            </motion.div>
            <span className="text-2xl font-bold text-primary group-hover:text-primary-600 transition-colors">
              MarketHub
            </span>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center gap-6">
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Link
                href="/search"
                className="text-gray-700 hover:text-primary transition-colors font-medium flex items-center gap-1"
              >
                <Search className="h-4 w-4" />
                {t('nav.search')}
              </Link>
            </motion.div>
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Link
                href="/products"
                className="text-gray-700 hover:text-primary transition-colors font-medium"
              >
                {t('nav.products')}
              </Link>
            </motion.div>
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Link
                href="/stores"
                className="text-gray-700 hover:text-primary transition-colors font-medium"
              >
                {t('nav.stores')}
              </Link>
            </motion.div>
            {/* Phase 13: anyone can post — the wizard is not seller-only. */}
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Link
                href="/post"
                className="btn-primary flex items-center gap-1 text-sm"
              >
                <Plus className="h-4 w-4" />
                {t('nav.postAd')}
              </Link>
            </motion.div>

            {isAuthenticated ? (
              <>
                {isSeller && (
                  <motion.div
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                  >
                    <Link
                      href="/seller/dashboard"
                      className="text-gray-700 hover:text-primary transition-colors font-medium"
                    >
                      {t('nav.dashboard')}
                    </Link>
                  </motion.div>
                )}
                {!isSeller && (
                  <>
                    <motion.div
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      <Link
                        href="/wishlist"
                        className="text-gray-700 hover:text-primary transition-colors flex items-center relative"
                        title={t('nav.wishlist')}
                      >
                        <Heart className="h-5 w-5" />
                      </Link>
                    </motion.div>
                    <motion.div
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      <Link
                        href="/cart"
                        className="text-gray-700 hover:text-primary transition-colors flex items-center relative"
                        title={t('nav.cart')}
                      >
                        <ShoppingCart className="h-5 w-5" />
                      </Link>
                    </motion.div>
                  </>
                )}
                <motion.div
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <Link
                    href="/messages"
                    className="relative flex items-center text-gray-700 transition-colors hover:text-primary"
                    title={t('nav.messages')}
                    aria-label={t('nav.messages')}
                  >
                    <MessageSquare className="h-5 w-5" />
                    {unreadBadge()}
                  </Link>
                </motion.div>
                <div className="relative group">
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    className="flex items-center gap-1 text-gray-700 hover:text-primary transition-colors font-medium"
                  >
                    <User className="h-5 w-5" />
                    <span>{user?.first_name || user?.email}</span>
                  </motion.button>
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="absolute end-0 mt-2 w-48 bg-white rounded-lg shadow-xl py-1 hidden group-hover:block border border-gray-100"
                  >
                    <Link
                      href="/profile"
                      className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      {t('nav.profile')}
                    </Link>
                    <Link
                      href="/orders"
                      className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      {t('nav.orders')}
                    </Link>
                    <Link
                      href="/messages"
                      className="flex items-center justify-between px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      <span>{t('nav.messages')}</span>
                      {unreadCount > 0 && (
                        <span className="rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">
                          {unreadCount > 99 ? '99+' : unreadCount}
                        </span>
                      )}
                    </Link>
                    <Link
                      href="/profile/saved-searches"
                      className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      {t('nav.savedSearches')}
                    </Link>
                    <button
                      onClick={logout}
                      className="block w-full text-start px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      {t('nav.logout')}
                    </button>
                  </motion.div>
                </div>
              </>
            ) : (
              <>
                <motion.div
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <Link
                    href="/login"
                    className="text-gray-700 hover:text-primary transition-colors font-medium"
                  >
                    {t('nav.login')}
                  </Link>
                </motion.div>
                <motion.div
                  whileHover={{ scale: 1.08 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <Link href="/register" className="btn-primary">
                    {t('nav.register')}
                  </Link>
                </motion.div>
              </>
            )}

            <LanguageSwitcher />
          </div>

          {/* Mobile menu button */}
          <div className="flex items-center gap-1 md:hidden">
            <LanguageSwitcher />
            <motion.button
              whileTap={{ scale: 0.95 }}
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label={
                mobileMenuOpen ? t('nav.closeMenu') : t('nav.openMenu')
              }
              className="p-2 rounded-md text-gray-700 hover:bg-gray-100 transition-colors"
            >
              <AnimatePresence mode="wait">
                {mobileMenuOpen ? (
                  <motion.div
                    key="close"
                    initial={{ rotate: -90, opacity: 0 }}
                    animate={{ rotate: 0, opacity: 1 }}
                    exit={{ rotate: 90, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <X className="h-6 w-6" />
                  </motion.div>
                ) : (
                  <motion.div
                    key="menu"
                    initial={{ rotate: 90, opacity: 0 }}
                    animate={{ rotate: 0, opacity: 1 }}
                    exit={{ rotate: -90, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <Menu className="h-6 w-6" />
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.button>
          </div>
        </div>

        {/* Mobile Navigation */}
        <AnimatePresence>
          {mobileMenuOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: 'easeInOut' }}
              className="md:hidden overflow-hidden border-t border-gray-200"
            >
              <motion.div
                initial={{ y: -20 }}
                animate={{ y: 0 }}
                exit={{ y: -20 }}
                transition={{ delay: 0.1 }}
                className="py-4 flex flex-col gap-3"
              >
                <motion.div whileHover={{ x: 5 }} whileTap={{ scale: 0.98 }}>
                  <Link
                    href="/search"
                    className="text-gray-700 hover:text-primary transition-colors font-medium block py-2"
                  >
                    {t('nav.search')}
                  </Link>
                </motion.div>
                <motion.div whileHover={{ x: 5 }} whileTap={{ scale: 0.98 }}>
                  <Link
                    href="/products"
                    className="text-gray-700 hover:text-primary transition-colors font-medium block py-2"
                  >
                    {t('nav.products')}
                  </Link>
                </motion.div>
                <motion.div whileHover={{ x: 5 }} whileTap={{ scale: 0.98 }}>
                  <Link
                    href="/stores"
                    className="text-gray-700 hover:text-primary transition-colors font-medium block py-2"
                  >
                    {t('nav.stores')}
                  </Link>
                </motion.div>
                <motion.div whileHover={{ x: 5 }} whileTap={{ scale: 0.98 }}>
                  <Link
                    href="/post"
                    className="text-primary hover:text-secondary transition-colors font-medium block py-2"
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    {t('nav.postAd')}
                  </Link>
                </motion.div>

                {isAuthenticated ? (
                  <>
                    {isSeller && (
                      <motion.div
                        whileHover={{ x: 5 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        <Link
                          href="/seller/dashboard"
                          className="text-gray-700 hover:text-primary transition-colors font-medium block py-2"
                        >
                          {t('nav.dashboard')}
                        </Link>
                      </motion.div>
                    )}
                    {!isSeller && (
                      <>
                        <motion.div
                          whileHover={{ x: 5 }}
                          whileTap={{ scale: 0.98 }}
                        >
                          <Link
                            href="/wishlist"
                            className="text-gray-700 hover:text-primary transition-colors font-medium block py-2"
                          >
                            {t('nav.wishlist')}
                          </Link>
                        </motion.div>
                        <motion.div
                          whileHover={{ x: 5 }}
                          whileTap={{ scale: 0.98 }}
                        >
                          <Link
                            href="/cart"
                            className="text-gray-700 hover:text-primary transition-colors font-medium block py-2"
                          >
                            {t('nav.cart')}
                          </Link>
                        </motion.div>
                      </>
                    )}
                    <motion.div
                      whileHover={{ x: 5 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      <Link
                        href="/profile"
                        className="text-gray-700 hover:text-primary transition-colors font-medium block py-2"
                      >
                        {t('nav.profile')}
                      </Link>
                    </motion.div>
                    <motion.div
                      whileHover={{ x: 5 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      <Link
                        href="/orders"
                        className="text-gray-700 hover:text-primary transition-colors font-medium block py-2"
                      >
                        {t('nav.orders')}
                      </Link>
                    </motion.div>
                    <motion.div
                      whileHover={{ x: 5 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      <Link
                        href="/messages"
                        className="flex items-center gap-2 text-gray-700 hover:text-primary transition-colors font-medium py-2"
                      >
                        {t('nav.messages')}
                        {unreadCount > 0 && (
                          <span className="rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">
                            {unreadCount > 99 ? '99+' : unreadCount}
                          </span>
                        )}
                      </Link>
                    </motion.div>
                    <motion.div
                      whileHover={{ x: 5 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      <Link
                        href="/profile/saved-searches"
                        className="text-gray-700 hover:text-primary transition-colors font-medium block py-2"
                      >
                        {t('nav.savedSearches')}
                      </Link>
                    </motion.div>
                    <motion.button
                      whileTap={{ scale: 0.98 }}
                      onClick={logout}
                      className="text-start text-gray-700 hover:text-primary transition-colors font-medium py-2"
                    >
                      {t('nav.logout')}
                    </motion.button>
                  </>
                ) : (
                  <>
                    <motion.div
                      whileHover={{ x: 5 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      <Link
                        href="/login"
                        className="text-gray-700 hover:text-primary transition-colors font-medium block py-2"
                      >
                        {t('nav.login')}
                      </Link>
                    </motion.div>
                    <motion.div
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      <Link
                        href="/register"
                        className="btn-primary inline-block text-center w-full"
                      >
                        {t('nav.register')}
                      </Link>
                    </motion.div>
                  </>
                )}
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </nav>
    </motion.header>
  )
}
