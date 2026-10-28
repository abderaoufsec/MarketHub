'use client'

import { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import { productsAPI } from '../../lib/api'
import { Search, Filter, ChevronDown } from 'lucide-react'
import ProductCard from '../../components/product/ProductCard'
import SkeletonLoader from '../../components/common/SkeletonLoader'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'
import { useTranslations } from 'next-intl'
import {
  fetchCategoryTree,
  categoryBySlug,
  effectiveDefinitions,
} from '../../lib/catalog'
import { fetchWilayas } from '../../lib/geography'

export default function ProductsPage() {
  const t = useTranslations('products')
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [categoryTree, setCategoryTree] = useState([])
  // Phase 13: `?wilaya=<id>` narrows the feed to one wilaya — the classifieds
  // answer to "near me" (same empty-page-not-500 contract as ?category=).
  const [wilayas, setWilayas] = useState([])
  // `category` is a catalog *slug* since Phase 12 (`?category=<slug>` matches
  // the node and every descendant server-side); attribute filters ride along
  // as `attr_<key>` / `attr_<key>_min` / `attr_<key>_max`.
  const [filters, setFilters] = useState({
    category: '',
    min_price: '',
    max_price: '',
    in_stock: true,
    wilaya: '',
    attributes: {},
  })
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchCategoryTree()
      .then((tree) => {
        if (!cancelled) setCategoryTree(tree)
      })
      .catch(() => {
        // Sidebar degrades to price/stock filters if the tree fails to load.
      })
    fetchWilayas()
      .then((rows) => {
        if (!cancelled) setWilayas(rows)
      })
      .catch(() => {
        // …and to no location filter at all.
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    fetchProducts()
  }, [search, filters])

  // Filterable attributes of the *selected* category (its own +
  // ancestors'), from the already-cached tree — no extra request when the
  // sidebar re-renders on every keystroke.
  const selectedNode = categoryBySlug(filters.category)
  const attributeDefinitions = useMemo(
    () =>
      effectiveDefinitions(selectedNode?.id)
        .filter((definition) => definition.filterable)
        .filter((definition) =>
          ['text', 'number', 'year', 'enum', 'range'].includes(definition.type)
        ),
    [selectedNode?.id]
  )

  const fetchProducts = async () => {
    try {
      setLoading(true)
      const params = {
        search: search || undefined,
        category: filters.category || undefined,
        min_price: filters.min_price || undefined,
        max_price: filters.max_price || undefined,
        in_stock: filters.in_stock || undefined,
        wilaya: filters.wilaya || undefined,
      }
      for (const [key, value] of Object.entries(filters.attributes)) {
        if (value === '' || value == null) continue
        if (typeof value === 'object') {
          if (value.min != null && value.min !== '') {
            params[`attr_${key}_min`] = value.min
          }
          if (value.max != null && value.max !== '') {
            params[`attr_${key}_max`] = value.max
          }
        } else {
          params[`attr_${key}`] = value
        }
      }
      const response = await productsAPI.list(params)
      setProducts(response.data.results || response.data)
      if (response.data.results?.length === 0 || response.data?.length === 0) {
        toast(t('noResultsToast'), { icon: '🔍' })
      }
    } catch (error) {
      console.error('Error fetching products:', error)
      setProducts([])
      toast.error(t('loadError'))
    } finally {
      setLoading(false)
    }
  }

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    fetchProducts()
  }

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }))
  }

  const handleCategoryChange = (slug) => {
    // Switching subtree invalidates attribute filters whose keys the new
    // category may not even define (the API answers 400 for unknown keys).
    setFilters((prev) => ({ ...prev, category: slug, attributes: {} }))
  }

  const handleAttributeChange = (key, value) => {
    setFilters((prev) => ({
      ...prev,
      attributes: { ...prev.attributes, [key]: value },
    }))
  }

  // Depth-first flatten with indent levels, like CategoryPicker does.
  const categoryOptions = []
  const pushCategories = (list, depth) => {
    for (const node of list) {
      categoryOptions.push(
        <option key={node.slug} value={node.slug}>
          {'\u00A0'.repeat(2 * depth) + node.name}
        </option>
      )
      if (node.children?.length) pushCategories(node.children, depth + 1)
    }
  }
  pushCategories(categoryTree, 0)

  const resetFilters = () => {
    setSearch('')
    setFilters({
      category: '',
      min_price: '',
      max_price: '',
      in_stock: true,
      wilaya: '',
      attributes: {},
    })
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8"
    >
      <motion.h1
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.1 }}
        className="text-4xl md:text-5xl font-bold text-gray-900 mb-8 gradient-text"
      >
        {t('title')}
      </motion.h1>

      {/* Search Bar */}
      <motion.form
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        onSubmit={handleSearchSubmit}
        className="mb-6"
      >
        <div className="flex gap-2">
          <motion.div whileFocus={{ scale: 1.01 }} className="flex-1 relative">
            <Search className="absolute start-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
            <input
              type="text"
              placeholder={t('searchPlaceholder')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full ps-10 pe-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary transition-all shadow-sm hover:shadow-md"
            />
          </motion.div>
          <motion.button
            type="button"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => setShowFilters(!showFilters)}
            className="btn-secondary flex items-center gap-2"
          >
            <Filter className="h-5 w-5" />
            {t('filters')}
            <motion.div
              animate={{ rotate: showFilters ? 180 : 0 }}
              transition={{ duration: 0.3 }}
            >
              <ChevronDown className="h-4 w-4" />
            </motion.div>
          </motion.button>
        </div>
      </motion.form>

      {/* Filters Panel */}
      <AnimatePresence>
        {showFilters && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="bg-white p-6 rounded-lg shadow-lg mb-6 grid grid-cols-1 md:grid-cols-4 gap-4 overflow-hidden border border-gray-100"
          >
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('categoryLabel')}
              </label>
              <select
                value={filters.category}
                onChange={(e) => handleCategoryChange(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
              >
                <option value="">{t('allCategories')}</option>
                {categoryOptions}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('minPrice')}
              </label>
              <input
                type="number"
                placeholder="0"
                value={filters.min_price}
                onChange={(e) =>
                  handleFilterChange('min_price', e.target.value)
                }
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('maxPrice')}
              </label>
              <input
                type="number"
                placeholder="1000"
                value={filters.max_price}
                onChange={(e) =>
                  handleFilterChange('max_price', e.target.value)
                }
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
              />
            </div>

            <div className="flex items-end">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={filters.in_stock}
                  onChange={(e) =>
                    handleFilterChange('in_stock', e.target.checked)
                  }
                  className="h-4 w-4 text-primary focus:ring-primary border-gray-300 rounded"
                />
                <span className="ms-2 text-sm text-gray-700">
                  {t('inStockOnly')}
                </span>
              </label>
            </div>

            {/* Phase 13: one wilaya, one feed. */}
            {wilayas.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('wilayaFilter')}
                </label>
                <select
                  value={filters.wilaya}
                  onChange={(e) => handleFilterChange('wilaya', e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                >
                  <option value="">{t('allWilayas')}</option>
                  {wilayas.map((wilaya) => (
                    <option key={wilaya.id} value={wilaya.id}>
                      {wilaya.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Category-specific attribute filters (Phase 12): labels come
                from the server, so admin edits show up with no deploy. */}
            {attributeDefinitions.map((definition) => (
              <AttributeFilter
                key={definition.key}
                definition={definition}
                value={filters.attributes[definition.key]}
                onChange={(value) =>
                  handleAttributeChange(definition.key, value)
                }
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Products Grid */}
      {loading ? (
        <SkeletonLoader variant="product" count={8} />
      ) : products.length > 0 ? (
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{
            visible: {
              transition: {
                staggerChildren: 0.1,
              },
            },
          }}
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6"
        >
          {products.map((product, index) => (
            <ProductCard key={product.id} product={product} index={index} />
          ))}
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center py-16"
        >
          <div className="inline-block p-6 bg-gray-100 rounded-full mb-4">
            <Search className="h-12 w-12 text-gray-400" />
          </div>
          <p className="text-gray-500 text-lg mb-4 font-medium">
            {t('empty.title')}
          </p>
          <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
            <Link
              href="/products"
              className="inline-block text-primary hover:text-secondary font-semibold transition-colors"
              onClick={resetFilters}
            >
              {t('empty.clearFilters')}
            </Link>
          </motion.div>
        </motion.div>
      )}
    </motion.div>
  )
}

/**
 * One filterable attribute in the sidebar: text → text input, number/year →
 * min/max bounds (`attr_k_min`/`_max`), enum → select, range → min/max
 * overlap bounds. Booleans are deliberately not filterable inputs here —
 * `?attr_flag=true` works, but a tri-state select adds more UI than it
 * earns in the sidebar; Phase 15's facet pass can revisit.
 */
function AttributeFilter({ definition, value, onChange }) {
  const tc = useTranslations('catalog')
  const { key, label, type, unit, choices = [] } = definition

  const labelNode = (
    <span className="block text-sm font-medium text-gray-700 mb-2">
      {label}
      {unit ? <span className="text-gray-400"> ({unit})</span> : null}
    </span>
  )

  if (type === 'enum') {
    return (
      <div>
        {labelNode}
        <select
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
        >
          <option value="">{tc('anyValue')}</option>
          {choices.map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </select>
      </div>
    )
  }

  if (type === 'range' || type === 'number' || type === 'year') {
    const bounds =
      value && typeof value === 'object' ? value : { min: '', max: '' }
    const commit = (next) => {
      const empty = !next.min && !next.max
      onChange(empty ? null : next)
    }
    return (
      <div>
        {labelNode}
        <div className="grid grid-cols-2 gap-2">
          <input
            type="number"
            placeholder={type === 'year' ? '1990' : tc('rangeMin')}
            value={bounds.min ?? ''}
            onChange={(e) => commit({ ...bounds, min: e.target.value })}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
          />
          <input
            type="number"
            placeholder={type === 'year' ? '2030' : tc('rangeMax')}
            value={bounds.max ?? ''}
            onChange={(e) => commit({ ...bounds, max: e.target.value })}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
          />
        </div>
      </div>
    )
  }

  return (
    <div>
      {labelNode}
      <input
        type="text"
        value={typeof value === 'string' ? value : ''}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
      />
    </div>
  )
}
