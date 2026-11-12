'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import {
  Store,
  ShoppingBag,
  TrendingUp,
  Shield,
  ArrowRight,
  Sparkles,
  Clock,
  Flame,
  LayoutGrid,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { useInView } from 'react-intersection-observer'
import { useTranslations } from 'next-intl'
import ProductCard from '../components/product/ProductCard'
import SkeletonLoader from '../components/common/SkeletonLoader'
import { feedAPI } from '../lib/api'

export default function Home() {
  const t = useTranslations('home')
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
            className="absolute top-0 start-0 w-96 h-96 bg-white rounded-full blur-3xl"
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
            className="absolute bottom-0 end-0 w-96 h-96 bg-secondary rounded-full blur-3xl"
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
            {t.rich('hero.title', {
              brand: (chunks) => (
                <span className="bg-clip-text text-transparent bg-gradient-to-r from-yellow-200 to-white">
                  {chunks}
                </span>
              ),
            })}
          </motion.h1>
          <motion.p
            variants={itemVariants}
            className="text-xl md:text-2xl mb-8 max-w-2xl mx-auto opacity-90"
          >
            {t('hero.subtitle')}
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
                {t('hero.browseProducts')}
                <ArrowRight className="h-5 w-5" />
              </Link>
            </motion.div>
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Link
                href="/register?seller=true"
                className="inline-flex items-center gap-2 bg-transparent border-2 border-white hover:bg-white hover:text-primary font-semibold py-3 px-8 rounded-lg transition-all backdrop-blur-sm"
              >
                {t('hero.becomeSeller')}
                <Store className="h-5 w-5" />
              </Link>
            </motion.div>
          </motion.div>
        </motion.div>
      </section>

      {/* Phase 15: real listings above the marketing copy - the home page is
          a discovery surface, not just a sign-up funnel. */}
      <FeedSections />

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
            {t('features.title')}
          </h2>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">
            {t('features.subtitle')}
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
              {t('features.selection.title')}
            </h3>
            <p className="text-gray-600 leading-relaxed">
              {t('features.selection.description')}
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
              {t('features.security.title')}
            </h3>
            <p className="text-gray-600 leading-relaxed">
              {t('features.security.description')}
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
              {t('features.selling.title')}
            </h3>
            <p className="text-gray-600 leading-relaxed">
              {t('features.selling.description')}
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
            className="absolute top-0 end-0 w-96 h-96 bg-primary rounded-full blur-3xl"
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
            {t('cta.title')}
          </motion.h2>
          <motion.p
            initial={{ opacity: 0 }}
            animate={ctaInView ? { opacity: 1 } : { opacity: 0 }}
            transition={{ delay: 0.2, duration: 0.6 }}
            className="text-lg md:text-xl text-gray-600 mb-10 max-w-2xl mx-auto"
          >
            {t('cta.subtitle')}
          </motion.p>
          <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
            <Link
              href="/register"
              className="inline-flex items-center gap-2 btn-primary text-lg py-4 px-10 text-lg font-bold shadow-xl"
            >
              {t('cta.createAccount')}
              <ArrowRight className="h-5 w-5" />
            </Link>
          </motion.div>
        </motion.div>
      </section>
    </div>
  )
}

function FeedSections() {
  const t = useTranslations('home.feed')
  const [sections, setSections] = useState({
    latest: { items: [], next: null, loading: true, error: false },
    trending: { items: [], next: null, loading: true, error: false },
  })
  const [categories, setCategories] = useState([])

  useEffect(() => {
    let cancelled = false
    const load = async (section) => {
      try {
        const response = await feedAPI.products({
          section,
          page_size: 8,
        })
        if (cancelled) return
        setSections((prev) => ({
          ...prev,
          [section]: {
            items: response.data.results || [],
            next: response.data.next || null,
            loading: false,
            error: false,
          },
        }))
      } catch {
        if (cancelled) return
        setSections((prev) => ({
          ...prev,
          [section]: { ...prev[section], loading: false, error: true },
        }))
      }
    }
    load('latest')
    load('trending')
    feedAPI
      .categories()
      .then((response) => {
        if (!cancelled) setCategories(response.data || [])
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const loadMore = async (section) => {
    const current = sections[section]
    if (!current.next || current.loadingMore) return
    setSections((prev) => ({
      ...prev,
      [section]: { ...prev[section], loadingMore: true },
    }))
    try {
      // The section's own `next` is a full cursor URL; following it is the
      // only way to paginate without rebuilding the ordering client-side.
      const response = await feedAPI.page(current.next)
      setSections((prev) => ({
        ...prev,
        [section]: {
          ...prev[section],
          items: [...prev[section].items, ...(response.data.results || [])],
          next: response.data.next || null,
          loadingMore: false,
        },
      }))
    } catch {
      setSections((prev) => ({
        ...prev,
        [section]: { ...prev[section], loadingMore: false },
      }))
    }
  }

  return (
    <section className="py-16 bg-gradient-to-b from-gray-50 to-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
          <div>
            <h2 className="text-3xl md:text-4xl font-bold gradient-text">
              {t('title')}
            </h2>
            <p className="text-gray-600 mt-2">{t('subtitle')}</p>
          </div>
          <Link
            href="/search"
            className="inline-flex items-center gap-2 text-primary font-semibold hover:underline"
          >
            {t('viewAll')}
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>

        {categories.length > 0 && (
          <div className="mb-10">
            <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-500 mb-3">
              <LayoutGrid className="h-4 w-4" />
              {t('categories')}
            </h3>
            <div className="flex flex-wrap gap-2">
              {categories.map((category) => (
                <Link
                  key={category.id}
                  href={`/search?category=${encodeURIComponent(category.slug)}`}
                  className="inline-flex items-center gap-2 bg-white border border-gray-200 hover:border-primary text-gray-700 hover:text-primary rounded-full px-4 py-2 text-sm shadow-sm transition-colors"
                >
                  {category.name}
                  <span className="text-xs text-gray-400">
                    {category.count}
                  </span>
                </Link>
              ))}
            </div>
          </div>
        )}

        <FeedRow
          icon={<Clock className="h-5 w-5 text-primary" />}
          title={t('latest')}
          state={sections.latest}
          onLoadMore={() => loadMore('latest')}
          t={t}
        />
        <FeedRow
          icon={<Flame className="h-5 w-5 text-orange-500" />}
          title={t('trending')}
          state={sections.trending}
          onLoadMore={() => loadMore('trending')}
          t={t}
        />
      </div>
    </section>
  )
}

function FeedRow({ icon, title, state, onLoadMore, t }) {
  return (
    <div className="mb-12 last:mb-0">
      <h3 className="flex items-center gap-2 text-xl font-bold text-gray-900 mb-4">
        {icon}
        {title}
      </h3>
      {state.loading ? (
        <SkeletonLoader variant="product" count={4} />
      ) : state.error ? (
        <p className="text-sm text-gray-500">{t('error')}</p>
      ) : state.items.length === 0 ? (
        <p className="text-sm text-gray-500">{t('empty')}</p>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {state.items.map((product, index) => (
              <ProductCard key={product.id} product={product} index={index} />
            ))}
          </div>
          {state.next && (
            <div className="text-center mt-5">
              <button
                type="button"
                onClick={onLoadMore}
                disabled={state.loadingMore}
                className="text-sm font-medium text-primary hover:underline disabled:opacity-50"
              >
                {state.loadingMore ? t('loadingMore') : t('loadMore')}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
