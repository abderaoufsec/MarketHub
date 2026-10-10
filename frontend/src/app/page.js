'use client'

import Link from 'next/link'
import {
  Store,
  ShoppingBag,
  TrendingUp,
  Shield,
  ArrowRight,
  Sparkles,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { useInView } from 'react-intersection-observer'

export default function Home() {
  const [heroRef, heroInView] = useInView({ threshold: 0.2, triggerOnce: true })
  const [featuresRef, featuresInView] = useInView({
    threshold: 0.2,
    triggerOnce: true,
  })
  const [ctaRef, ctaInView] = useInView({ threshold: 0.2, triggerOnce: true })

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
        duration: 0.5,
      },
    },
  }

  return (
    <div className="overflow-hidden">
      {/* Hero Section */}
      <section className="relative bg-gradient-to-br from-primary via-primary-600 to-secondary text-white py-20 overflow-hidden">
        {/* Animated background elements */}
        <div className="absolute inset-0 overflow-hidden">
          <motion.div
            animate={{
              scale: [1, 1.2, 1],
              rotate: [0, 90, 0],
              opacity: [0.1, 0.2, 0.1],
            }}
            transition={{
              duration: 20,
              repeat: Infinity,
              ease: 'linear',
            }}
            className="absolute top-0 left-0 w-96 h-96 bg-white rounded-full blur-3xl"
          />
          <motion.div
            animate={{
              scale: [1, 1.3, 1],
              rotate: [0, -90, 0],
              opacity: [0.1, 0.2, 0.1],
            }}
            transition={{
              duration: 25,
              repeat: Infinity,
              ease: 'linear',
            }}
            className="absolute bottom-0 right-0 w-96 h-96 bg-secondary rounded-full blur-3xl"
          />
        </div>

        <motion.div
          ref={heroRef}
          initial="hidden"
          animate={heroInView ? 'visible' : 'hidden'}
          variants={containerVariants}
          className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center"
        >
          <motion.div variants={itemVariants} className="mb-4">
            <Sparkles className="h-8 w-8 mx-auto text-yellow-300" />
          </motion.div>
          <motion.h1
            variants={itemVariants}
            className="text-5xl md:text-6xl lg:text-7xl font-bold mb-6 leading-tight"
          >
            Welcome to{' '}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-yellow-200 to-white">
              MarketHub
            </span>
          </motion.h1>
          <motion.p
            variants={itemVariants}
            className="text-xl md:text-2xl mb-8 max-w-2xl mx-auto opacity-90"
          >
            Your trusted online marketplace connecting buyers and sellers.
            Discover unique products or start selling today.
          </motion.p>
          <motion.div
            variants={itemVariants}
            className="flex flex-col sm:flex-row gap-4 justify-center"
          >
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Link
                href="/products"
                className="inline-flex items-center gap-2 bg-white text-primary hover:bg-gray-100 font-semibold py-3 px-8 rounded-lg transition-all shadow-lg hover:shadow-xl"
              >
                Browse Products
                <ArrowRight className="h-5 w-5" />
              </Link>
            </motion.div>
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Link
                href="/register?seller=true"
                className="inline-flex items-center gap-2 bg-transparent border-2 border-white hover:bg-white hover:text-primary font-semibold py-3 px-8 rounded-lg transition-all backdrop-blur-sm"
              >
                Become a Seller
                <Store className="h-5 w-5" />
              </Link>
            </motion.div>
          </motion.div>
        </motion.div>
      </section>

      {/* Features Section */}
      <section
        ref={featuresRef}
        className="py-20 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8"
      >
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={
            featuresInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }
          }
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl md:text-5xl font-bold mb-4 gradient-text">
            Why Choose MarketHub?
          </h2>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">
            Experience the difference with our professional marketplace platform
          </p>
        </motion.div>
        <motion.div
          initial="hidden"
          animate={featuresInView ? 'visible' : 'hidden'}
          variants={containerVariants}
          className="grid grid-cols-1 md:grid-cols-3 gap-8"
        >
          <motion.div
            variants={itemVariants}
            whileHover={{ y: -10, scale: 1.02 }}
            className="text-center p-8 rounded-xl bg-white shadow-lg hover:shadow-2xl transition-all duration-300 border border-gray-100 group"
          >
            <motion.div
              whileHover={{ rotate: [0, -10, 10, -10, 0], scale: 1.1 }}
              transition={{ duration: 0.5 }}
              className="inline-block p-4 bg-gradient-to-br from-blue-100 to-blue-200 rounded-2xl mb-6 group-hover:from-blue-200 group-hover:to-blue-300 transition-all"
            >
              <ShoppingBag className="h-10 w-10 text-primary" />
            </motion.div>
            <h3 className="text-2xl font-bold mb-3 text-gray-900 group-hover:text-primary transition-colors">
              Wide Selection
            </h3>
            <p className="text-gray-600 leading-relaxed">
              Browse thousands of products from verified sellers across multiple
              categories.
            </p>
          </motion.div>
          <motion.div
            variants={itemVariants}
            whileHover={{ y: -10, scale: 1.02 }}
            className="text-center p-8 rounded-xl bg-white shadow-lg hover:shadow-2xl transition-all duration-300 border border-gray-100 group"
          >
            <motion.div
              whileHover={{ rotate: [0, -10, 10, -10, 0], scale: 1.1 }}
              transition={{ duration: 0.5 }}
              className="inline-block p-4 bg-gradient-to-br from-green-100 to-green-200 rounded-2xl mb-6 group-hover:from-green-200 group-hover:to-green-300 transition-all"
            >
              <Shield className="h-10 w-10 text-green-600" />
            </motion.div>
            <h3 className="text-2xl font-bold mb-3 text-gray-900 group-hover:text-green-600 transition-colors">
              Secure Shopping
            </h3>
            <p className="text-gray-600 leading-relaxed">
              Shop with confidence knowing your transactions are protected and
              secure.
            </p>
          </motion.div>
          <motion.div
            variants={itemVariants}
            whileHover={{ y: -10, scale: 1.02 }}
            className="text-center p-8 rounded-xl bg-white shadow-lg hover:shadow-2xl transition-all duration-300 border border-gray-100 group"
          >
            <motion.div
              whileHover={{ rotate: [0, -10, 10, -10, 0], scale: 1.1 }}
              transition={{ duration: 0.5 }}
              className="inline-block p-4 bg-gradient-to-br from-purple-100 to-purple-200 rounded-2xl mb-6 group-hover:from-purple-200 group-hover:to-purple-300 transition-all"
            >
              <TrendingUp className="h-10 w-10 text-purple-600" />
            </motion.div>
            <h3 className="text-2xl font-bold mb-3 text-gray-900 group-hover:text-purple-600 transition-colors">
              Easy Selling
            </h3>
            <p className="text-gray-600 leading-relaxed">
              Start your online store quickly and manage your products with
              ease.
            </p>
          </motion.div>
        </motion.div>
      </section>

      {/* CTA Section */}
      <section
        ref={ctaRef}
        className="relative bg-gradient-to-r from-gray-50 to-gray-100 py-20 overflow-hidden"
      >
        <div className="absolute inset-0">
          <motion.div
            animate={{
              x: [0, 100, 0],
              opacity: [0.1, 0.2, 0.1],
            }}
            transition={{
              duration: 15,
              repeat: Infinity,
              ease: 'linear',
            }}
            className="absolute top-0 right-0 w-96 h-96 bg-primary rounded-full blur-3xl"
          />
        </div>
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={ctaInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
          transition={{ duration: 0.6 }}
          className="relative max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center"
        >
          <motion.h2
            whileInView={{ scale: [1, 1.05, 1] }}
            transition={{ duration: 0.5 }}
            className="text-4xl md:text-5xl font-bold mb-4 text-gray-900"
          >
            Ready to Get Started?
          </motion.h2>
          <motion.p
            initial={{ opacity: 0 }}
            animate={ctaInView ? { opacity: 1 } : { opacity: 0 }}
            transition={{ delay: 0.2, duration: 0.6 }}
            className="text-lg md:text-xl text-gray-600 mb-10 max-w-2xl mx-auto"
          >
            Join thousands of buyers and sellers on MarketHub today.
          </motion.p>
          <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
            <Link
              href="/register"
              className="inline-flex items-center gap-2 btn-primary text-lg py-4 px-10 text-lg font-bold shadow-xl"
            >
              Create Your Account
              <ArrowRight className="h-5 w-5" />
            </Link>
          </motion.div>
        </motion.div>
      </section>
    </div>
  )
}
