'use client'

import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'
import { Store, Mail, Facebook, Twitter, Instagram } from 'lucide-react'
import { motion } from 'framer-motion'
import { dirFor } from '../../i18n/config'

export default function Footer() {
  const t = useTranslations('common')
  const locale = useLocale()
  // Phase 11: slide-in animations follow the reading direction.
  const enterX = dirFor(locale) === 'rtl' ? 20 : -20

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
      },
    },
  }

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        duration: 0.4,
      },
    },
  }

  return (
    <footer className="bg-gradient-to-b from-gray-900 to-gray-800 text-gray-300">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: '-100px' }}
          variants={containerVariants}
          className="grid grid-cols-1 md:grid-cols-4 gap-8"
        >
          {/* Brand */}
          <motion.div variants={itemVariants} className="col-span-1">
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Link href="/" className="flex items-center gap-2 mb-4 group">
                <motion.div
                  whileHover={{ rotate: [0, -10, 10, -10, 0] }}
                  transition={{ duration: 0.5 }}
                >
                  <Store className="h-8 w-8 text-primary group-hover:text-primary-400 transition-colors" />
                </motion.div>
                <span className="text-2xl font-bold text-white group-hover:text-primary-400 transition-colors">
                  MarketHub
                </span>
              </Link>
            </motion.div>
            <p className="text-sm leading-relaxed opacity-90">
              {t('footer.tagline')}
            </p>
          </motion.div>

          {/* Quick Links */}
          <motion.div variants={itemVariants}>
            <h3 className="text-white font-semibold mb-4 text-lg">
              {t('footer.quickLinks')}
            </h3>
            <ul className="space-y-3 text-sm">
              {[
                { href: '/products', label: t('nav.products') },
                { href: '/stores', label: t('nav.stores') },
                { href: '/about', label: t('footer.aboutUs') },
              ].map((link, index) => (
                <motion.li
                  key={link.href}
                  initial={{ opacity: 0, x: enterX }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: index * 0.1 }}
                  whileHover={{ x: enterX > 0 ? -5 : 5 }}
                >
                  <Link
                    href={link.href}
                    className="hover:text-white transition-colors flex items-center group"
                  >
                    <span className="group-hover:text-primary transition-colors">
                      {link.label}
                    </span>
                  </Link>
                </motion.li>
              ))}
            </ul>
          </motion.div>

          {/* For Sellers */}
          <motion.div variants={itemVariants}>
            <h3 className="text-white font-semibold mb-4 text-lg">
              {t('footer.forSellers')}
            </h3>
            <ul className="space-y-3 text-sm">
              {[
                {
                  href: '/register?seller=true',
                  label: t('footer.becomeSeller'),
                },
                {
                  href: '/seller/dashboard',
                  label: t('footer.sellerDashboard'),
                },
                { href: '/help/sellers', label: t('footer.sellerHelp') },
              ].map((link, index) => (
                <motion.li
                  key={link.href}
                  initial={{ opacity: 0, x: enterX }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: index * 0.1 }}
                  whileHover={{ x: enterX > 0 ? -5 : 5 }}
                >
                  <Link
                    href={link.href}
                    className="hover:text-white transition-colors flex items-center group"
                  >
                    <span className="group-hover:text-primary transition-colors">
                      {link.label}
                    </span>
                  </Link>
                </motion.li>
              ))}
            </ul>
          </motion.div>

          {/* Contact */}
          <motion.div variants={itemVariants}>
            <h3 className="text-white font-semibold mb-4 text-lg">
              {t('footer.contact')}
            </h3>
            <ul className="space-y-3 text-sm">
              <motion.li
                initial={{ opacity: 0, x: enterX }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                className="flex items-center gap-2 group"
              >
                <Mail className="h-4 w-4 group-hover:text-primary transition-colors" />
                <a
                  href="mailto:support@markethub.com"
                  className="hover:text-white transition-colors group-hover:text-primary"
                  dir="ltr"
                >
                  support@markethub.com
                </a>
              </motion.li>
            </ul>
            <div className="flex gap-4 mt-6">
              {[
                { Icon: Facebook, href: '#' },
                { Icon: Twitter, href: '#' },
                { Icon: Instagram, href: '#' },
              ].map(({ Icon, href }, index) => (
                <motion.a
                  key={index}
                  href={href}
                  whileHover={{ scale: 1.2, y: -3 }}
                  whileTap={{ scale: 0.9 }}
                  className="hover:text-white transition-colors hover:text-primary"
                >
                  <Icon className="h-5 w-5" />
                </motion.a>
              ))}
            </div>
          </motion.div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.3 }}
          className="border-t border-gray-800 mt-8 pt-8 text-sm text-center"
        >
          <p className="mb-4 opacity-80">
            {t('footer.rights', { year: new Date().getFullYear() })}
          </p>
          <div className="flex justify-center gap-6">
            {[
              { href: '/privacy', label: t('footer.privacy') },
              { href: '/terms', label: t('footer.terms') },
            ].map((link) => (
              <motion.div
                key={link.href}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <Link
                  href={link.href}
                  className="hover:text-white transition-colors hover:text-primary font-medium"
                >
                  {link.label}
                </Link>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </footer>
  )
}
