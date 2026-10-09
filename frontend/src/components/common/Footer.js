'use client'

import Link from 'next/link'
import { Store, Mail, Facebook, Twitter, Instagram } from 'lucide-react'
import { motion } from 'framer-motion'

export default function Footer() {
  const currentYear = new Date().getFullYear()

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
          viewport={{ once: true, margin: "-100px" }}
          variants={containerVariants}
          className="grid grid-cols-1 md:grid-cols-4 gap-8"
        >
          {/* Brand */}
          <motion.div variants={itemVariants} className="col-span-1">
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Link href="/" className="flex items-center space-x-2 mb-4 group">
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
              Your trusted online marketplace connecting buyers and sellers.
            </p>
          </motion.div>

          {/* Quick Links */}
          <motion.div variants={itemVariants}>
            <h3 className="text-white font-semibold mb-4 text-lg">Quick Links</h3>
            <ul className="space-y-3 text-sm">
              {[
                { href: '/products', label: 'Products' },
                { href: '/stores', label: 'Stores' },
                { href: '/about', label: 'About Us' },
              ].map((link, index) => (
                <motion.li
                  key={link.href}
                  initial={{ opacity: 0, x: -20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: index * 0.1 }}
                  whileHover={{ x: 5 }}
                >
                  <Link
                    href={link.href}
                    className="hover:text-white transition-colors flex items-center group"
                  >
                    <span className="group-hover:text-primary transition-colors">{link.label}</span>
                  </Link>
                </motion.li>
              ))}
            </ul>
          </motion.div>

          {/* For Sellers */}
          <motion.div variants={itemVariants}>
            <h3 className="text-white font-semibold mb-4 text-lg">For Sellers</h3>
            <ul className="space-y-3 text-sm">
              {[
                { href: '/register?seller=true', label: 'Become a Seller' },
                { href: '/seller/dashboard', label: 'Seller Dashboard' },
                { href: '/help/sellers', label: 'Seller Help' },
              ].map((link, index) => (
                <motion.li
                  key={link.href}
                  initial={{ opacity: 0, x: -20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: index * 0.1 }}
                  whileHover={{ x: 5 }}
                >
                  <Link
                    href={link.href}
                    className="hover:text-white transition-colors flex items-center group"
                  >
                    <span className="group-hover:text-primary transition-colors">{link.label}</span>
                  </Link>
                </motion.li>
              ))}
            </ul>
          </motion.div>

          {/* Contact */}
          <motion.div variants={itemVariants}>
            <h3 className="text-white font-semibold mb-4 text-lg">Contact</h3>
            <ul className="space-y-3 text-sm">
              <motion.li
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                className="flex items-center space-x-2 group"
              >
                <Mail className="h-4 w-4 group-hover:text-primary transition-colors" />
                <a
                  href="mailto:support@markethub.com"
                  className="hover:text-white transition-colors group-hover:text-primary"
                >
                  support@markethub.com
                </a>
              </motion.li>
            </ul>
            <div className="flex space-x-4 mt-6">
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
          <p className="mb-4 opacity-80">&copy; {currentYear} MarketHub. All rights reserved.</p>
          <div className="flex justify-center space-x-6">
            {[
              { href: '/privacy', label: 'Privacy Policy' },
              { href: '/terms', label: 'Terms of Service' },
            ].map((link) => (
              <motion.div key={link.href} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
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
