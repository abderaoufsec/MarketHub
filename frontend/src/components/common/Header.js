'use client'

import Link from 'next/link'
import { useAuth } from '../../context/AuthContext'
import { ShoppingCart, User, Store, Menu, X, Heart } from 'lucide-react'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

export default function Header() {
  const { user, isAuthenticated, isSeller, logout } = useAuth()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

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
          <Link href="/" className="flex items-center space-x-2 group">
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
          <div className="hidden md:flex items-center space-x-8">
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Link
                href="/products"
                className="text-gray-700 hover:text-primary transition-colors font-medium"
              >
                Products
              </Link>
            </motion.div>
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Link
                href="/stores"
                className="text-gray-700 hover:text-primary transition-colors font-medium"
              >
                Stores
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
                      Dashboard
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
                        title="Wishlist"
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
                        title="Cart"
                      >
                        <ShoppingCart className="h-5 w-5" />
                      </Link>
                    </motion.div>
                  </>
                )}
                <div className="relative group">
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    className="flex items-center space-x-1 text-gray-700 hover:text-primary transition-colors font-medium"
                  >
                    <User className="h-5 w-5" />
                    <span>{user?.first_name || user?.email}</span>
                  </motion.button>
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-xl py-1 hidden group-hover:block border border-gray-100"
                  >
                    <Link
                      href="/profile"
                      className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      Profile
                    </Link>
                    <Link
                      href="/orders"
                      className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      Orders
                    </Link>
                    <button
                      onClick={logout}
                      className="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      Logout
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
                    Login
                  </Link>
                </motion.div>
                <motion.div
                  whileHover={{ scale: 1.08 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <Link href="/register" className="btn-primary">
                    Register
                  </Link>
                </motion.div>
              </>
            )}
          </div>

          {/* Mobile menu button */}
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2 rounded-md text-gray-700 hover:bg-gray-100 transition-colors"
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
                className="py-4 flex flex-col space-y-3"
              >
                <motion.div whileHover={{ x: 5 }} whileTap={{ scale: 0.98 }}>
                  <Link
                    href="/products"
                    className="text-gray-700 hover:text-primary transition-colors font-medium block py-2"
                  >
                    Products
                  </Link>
                </motion.div>
                <motion.div whileHover={{ x: 5 }} whileTap={{ scale: 0.98 }}>
                  <Link
                    href="/stores"
                    className="text-gray-700 hover:text-primary transition-colors font-medium block py-2"
                  >
                    Stores
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
                          Dashboard
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
                            Wishlist
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
                            Cart
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
                        Profile
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
                        Orders
                      </Link>
                    </motion.div>
                    <motion.button
                      whileTap={{ scale: 0.98 }}
                      onClick={logout}
                      className="text-left text-gray-700 hover:text-primary transition-colors font-medium py-2"
                    >
                      Logout
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
                        Login
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
                        Register
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
