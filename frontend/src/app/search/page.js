'use client'

import { Suspense, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import {
  ArrowRight,
  Bookmark,
  LocateFixed,
  MapPin,
  Search,
  SlidersHorizontal,
  Sparkles,
  X,
} from 'lucide-react'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'
import { useTranslations } from 'next-intl'

import ProductCard from '../../components/product/ProductCard'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import SkeletonLoader from '../../components/common/SkeletonLoader'
import { useAuth } from '../../context/AuthContext'
import { searchAPI } from '../../lib/api'
import { fetchCategoryTree, flatCategories } from '../../lib/catalog'
import { fetchWilayas } from '../../lib/geography'

const BOOLEAN_KEYS = ['verified', 'with_photos', 'in_stock']
const SINGLE_KEYS = [
  'category',
  'wilaya',
  'condition',
  'seller_type',
  'posted',
  'sort',
]

const EMPTY_FILTERS = {
  q: '',
  category: '',
  wilaya: '',
  min_price: '',
  max_price: '',
  condition: '',
  seller_type: '',
  verified: '',
  with_photos: '',
  in_stock: '',
  posted: '',
  sort: '',
  lat: '',
  lng: '',
  attributes: {},
}

/**
 * `/search` - the real consumer of `productsAPI.search` (Phase 15).
 *
 * UI state is one filter object; the API params are derived from it and are
 * exactly what a saved search stores (`buildParams`). The suggestion dropdown
 * never writes analytics (the backend only records the full search), so typing
 * is cheap.
 */
export default function SearchPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <SearchExperience />
    </Suspense>
  )
}

function initialFilters(searchParams) {
  if (!searchParams) return { ...EMPTY_FILTERS, attributes: {} }
  const filters = { ...EMPTY_FILTERS, attributes: {} }
  for (const [key, value] of searchParams.entries()) {
    if (key.startsWith('attr_')) {
      filters.attributes[key.slice(5)] = value
    } else if (key in filters && key !== 'attributes') {
      filters[key] = value
    }
  }
  return filters
}

function buildParams(filters) {
  const params = {}
  if (filters.q.trim()) params.q = filters.q.trim()
  for (const key of [
    'category',
    'wilaya',
    'min_price',
    'max_price',
    'condition',
    'seller_type',
    'posted',
    'sort',
    'lat',
    'lng',
  ]) {
    if (filters[key] !== '' && filters[key] != null) params[key] = filters[key]
  }
  for (const key of BOOLEAN_KEYS) {
    if (filters[key] === 'true' || filters[key] === true) params[key] = 'true'
  }
  for (const [key, value] of Object.entries(filters.attributes || {})) {
    if (value !== '' && value != null) params[`attr_${key}`] = value
  }
  return params
}

function SearchExperience() {
  const t = useTranslations('search')
  const searchParams = useSearchParams()
  const { isAuthenticated, user } = useAuth()

  const [filters, setFilters] = useState(() => initialFilters(searchParams))
  const [qInput, setQInput] = useState(filters.q)
  const [products, setProducts] = useState([])
  const [facets, setFacets] = useState(null)
  const [meta, setMeta] = useState(null)
  const [next, setNext] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [categories, setCategories] = useState([])
  const [wilayas, setWilayas] = useState([])
  const [suggestions, setSuggestions] = useState(null)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [recent, setRecent] = useState([])
  const [saveOpen, setSaveOpen] = useState(false)
  const requestId = useRef(0)

  useEffect(() => {
    let cancelled = false
    fetchCategoryTree()
      .then(() => {
        if (!cancelled) setCategories(flatCategories())
      })
      .catch(() => {})
    fetchWilayas()
      .then((rows) => {
        if (!cancelled) setWilayas(rows)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  // One request per filter change; stale answers are dropped with a counter
  // rather than AbortController so a slow response cannot overwrite a fast one.
  useEffect(() => {
    const id = ++requestId.current
    setLoading(true)
    setNext(null)
    searchAPI
      .search(buildParams(filters))
      .then((response) => {
        if (id !== requestId.current) return
        setProducts(response.data.results || [])
        setFacets(response.data.facets || null)
        setMeta(response.data.meta || null)
        setNext(response.data.next || null)
      })
      .catch((error) => {
        if (id !== requestId.current) return
        console.error('Search failed:', error)
        setProducts([])
        setFacets(null)
        setMeta(null)
        toast.error(t('error'))
      })
      .finally(() => {
        if (id === requestId.current) setLoading(false)
      })
  }, [filters, t])

  // Autocomplete: 250 ms debounce, only for two or more characters.
  useEffect(() => {
    if (!showSuggestions || qInput.trim().length < 2) {
      setSuggestions(null)
      return undefined
    }
    let active = true
    const timer = setTimeout(() => {
      searchAPI
        .suggestions(qInput.trim())
        .then((response) => {
          if (active) setSuggestions(response.data)
        })
        .catch(() => {})
    }, 250)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [qInput, showSuggestions])

  const loadRecent = async () => {
    if (!isAuthenticated) return
    try {
      const response = await searchAPI.recent()
      setRecent(response.data)
    } catch {
      // Recent searches are a convenience; a failure is silent.
    }
  }

  const submitSearch = (event, value) => {
    event?.preventDefault()
    setShowSuggestions(false)
    const term = (typeof value === 'string' ? value : qInput).trim()
    setQInput(term)
    setFilters((prev) => ({ ...prev, q: term }))
  }

  const updateFilter = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }))
  }

  const toggleBoolean = (key) => {
    updateFilter(key, filters[key] === 'true' ? '' : 'true')
  }

  const clearFilters = () => {
    setQInput('')
    setFilters({ ...EMPTY_FILTERS, attributes: {} })
  }

  const categoryOptions = categories

  const removeRelaxation = (param) => {
    if (param === 'q') {
      setQInput('')
      updateFilter('q', '')
      return
    }
    if (param.startsWith('attr_')) {
      const key = param.slice(5)
      setFilters((prev) => {
        const attributes = { ...prev.attributes }
        delete attributes[key]
        return { ...prev, attributes }
      })
      return
    }
    if (param === 'min_price' || param === 'max_price') {
      setFilters((prev) => ({ ...prev, min_price: '', max_price: '' }))
      return
    }
    updateFilter(param, '')
  }

  const loadMore = async () => {
    if (!next || loadingMore) return
    const id = requestId.current
    setLoadingMore(true)
    try {
      const response = await searchAPI.page(next)
      // A filter change while this page was in flight starts a new result
      // set; appending the old cursor page would mix two searches.
      if (id !== requestId.current) return
      setProducts((prev) => [...prev, ...(response.data.results || [])])
      setNext(response.data.next || null)
    } catch (error) {
      console.error('Search page failed:', error)
      toast.error(t('error'))
    } finally {
      setLoadingMore(false)
    }
  }

  const locate = () => {
    if (!navigator.geolocation) {
      toast.error(t('geoUnsupported'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setFilters((prev) => ({
          ...prev,
          lat: position.coords.latitude.toFixed(5),
          lng: position.coords.longitude.toFixed(5),
          sort: 'distance',
        }))
      },
      () => toast.error(t('geoDenied'))
    )
  }

  const hasFilters =
    Object.keys(buildParams(filters)).length > 0 || qInput.trim() !== ''

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <h1 className="text-4xl md:text-5xl font-bold gradient-text mb-2">
          {t('title')}
        </h1>
        <p className="text-gray-600 mb-6">{t('subtitle')}</p>

        <form onSubmit={submitSearch} className="relative mb-4">
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Search className="absolute start-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="search"
                value={qInput}
                onChange={(event) => setQInput(event.target.value)}
                onFocus={() => {
                  setShowSuggestions(true)
                  if (!qInput.trim()) loadRecent()
                }}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                placeholder={t('placeholder')}
                aria-label={t('placeholder')}
                className="w-full ps-10 pe-10 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary shadow-sm"
              />
              {qInput && (
                <button
                  type="button"
                  onClick={() => setQInput('')}
                  aria-label={t('clearQuery')}
                  className="absolute end-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
            <button type="submit" className="btn-primary px-6">
              {t('submit')}
            </button>
            <button
              type="button"
              onClick={() => setShowFilters((value) => !value)}
              className="btn-secondary flex items-center gap-2 md:hidden"
            >
              <SlidersHorizontal className="h-4 w-4" />
              {t('filters')}
            </button>
          </div>

          {showSuggestions &&
            (qInput.trim().length >= 2 || recent.length > 0) && (
              <div className="absolute z-30 start-0 end-0 mt-1 bg-white rounded-lg shadow-xl border border-gray-100 overflow-hidden text-start">
                {recent.length > 0 && !qInput.trim() && (
                  <div className="p-3 border-b border-gray-100">
                    <p className="text-xs uppercase tracking-wide text-gray-400 mb-2">
                      {t('recent.title')}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {recent.map((row) => (
                        <button
                          key={row.id}
                          type="button"
                          className="text-sm bg-gray-100 hover:bg-gray-200 rounded-full px-3 py-1"
                          onClick={() => {
                            setQInput(row.query)
                            submitSearch(null, row.query)
                          }}
                        >
                          {row.query || t('recent.filtersOnly')}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {suggestions?.terms?.length > 0 && (
                  <div className="p-2">
                    {suggestions.terms.map((term) => (
                      <button
                        key={term}
                        type="button"
                        className="block w-full text-start px-3 py-2 text-sm hover:bg-gray-50 rounded"
                        onClick={() => {
                          setQInput(term)
                          submitSearch(null, term)
                        }}
                      >
                        {term}
                      </button>
                    ))}
                  </div>
                )}
                {suggestions?.products?.length > 0 && (
                  <div className="border-t border-gray-100 p-2">
                    {suggestions.products.map((product) => (
                      <Link
                        key={product.id}
                        href={product.canonical_path}
                        className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 rounded"
                      >
                        <span className="truncate">{product.name}</span>
                        {product.category && (
                          <span className="ms-auto text-xs text-gray-400">
                            {product.category}
                          </span>
                        )}
                      </Link>
                    ))}
                  </div>
                )}
                {suggestions?.did_you_mean && (
                  <button
                    type="button"
                    className="w-full text-start border-t border-gray-100 px-3 py-2 text-sm text-primary hover:bg-primary/5"
                    onClick={() => {
                      setQInput(suggestions.did_you_mean)
                      submitSearch(null, suggestions.did_you_mean)
                    }}
                  >
                    {t('didYouMean', { term: suggestions.did_you_mean })}
                  </button>
                )}
              </div>
            )}
        </form>

        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <p className="text-sm text-gray-600">
            {meta ? t('resultsCount', { count: meta.total }) : t('loading')}
          </p>
          <div className="flex items-center gap-2">
            {isAuthenticated ? (
              <button
                type="button"
                onClick={() => setSaveOpen(true)}
                className="btn-secondary flex items-center gap-2 text-sm"
              >
                <Bookmark className="h-4 w-4" />
                {t('saved.save')}
              </button>
            ) : (
              <Link
                href="/login?next=/search"
                className="btn-secondary flex items-center gap-2 text-sm"
              >
                <Bookmark className="h-4 w-4" />
                {t('saved.signInToSave')}
              </Link>
            )}
            <select
              value={filters.sort}
              onChange={(event) => updateFilter('sort', event.target.value)}
              aria-label={t('sort')}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">{t('sorts.default')}</option>
              <option value="newest">{t('sorts.newest')}</option>
              <option value="price_asc">{t('sorts.price_asc')}</option>
              <option value="price_desc">{t('sorts.price_desc')}</option>
              <option value="distance" disabled={!filters.lat || !filters.lng}>
                {t('sorts.distance')}
              </option>
            </select>
            <button
              type="button"
              onClick={locate}
              className="btn-secondary flex items-center gap-2 text-sm"
              title={t('nearMe')}
            >
              <LocateFixed className="h-4 w-4" />
              {t('nearMe')}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <aside
            className={`${showFilters ? 'block' : 'hidden'} lg:block lg:col-span-1`}
          >
            <div className="bg-white border border-gray-100 rounded-lg shadow-sm p-4 space-y-5 lg:sticky lg:top-20">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-gray-900">{t('filters')}</h2>
                {hasFilters && (
                  <button
                    type="button"
                    onClick={clearFilters}
                    className="text-xs text-primary hover:underline"
                  >
                    {t('clearFilters')}
                  </button>
                )}
              </div>

              <FacetSection title={t('category')}>
                <select
                  value={filters.category}
                  onChange={(event) =>
                    updateFilter('category', event.target.value)
                  }
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  <option value="">{t('allCategories')}</option>
                  {categoryOptions.map((node) => (
                    <option key={node.slug} value={node.slug}>
                      {'\u00A0'.repeat(2 * node.depth) + node.name}
                    </option>
                  ))}
                </select>
              </FacetSection>

              <FacetSection title={t('wilaya')}>
                <select
                  value={filters.wilaya}
                  onChange={(event) =>
                    updateFilter('wilaya', event.target.value)
                  }
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  <option value="">{t('allWilayas')}</option>
                  {wilayas.map((wilaya) => (
                    <option key={wilaya.id} value={wilaya.id}>
                      {wilaya.name}
                    </option>
                  ))}
                </select>
              </FacetSection>

              <FacetSection title={t('price')}>
                <div className="flex gap-2">
                  <input
                    type="number"
                    inputMode="numeric"
                    placeholder={t('minPrice')}
                    value={filters.min_price}
                    onChange={(event) =>
                      updateFilter('min_price', event.target.value)
                    }
                    className="w-1/2 border border-gray-300 rounded-lg px-2 py-2 text-sm"
                  />
                  <input
                    type="number"
                    inputMode="numeric"
                    placeholder={t('maxPrice')}
                    value={filters.max_price}
                    onChange={(event) =>
                      updateFilter('max_price', event.target.value)
                    }
                    className="w-1/2 border border-gray-300 rounded-lg px-2 py-2 text-sm"
                  />
                </div>
                {facets?.price?.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {facets.price.map((bucket) => (
                      <button
                        key={bucket.value}
                        type="button"
                        disabled={bucket.count === 0}
                        onClick={() => {
                          const bands = {
                            under_5k: ['', '5000'],
                            '5k_20k': ['5000', '20000'],
                            '20k_100k': ['20000', '100000'],
                            over_100k: ['100000', ''],
                          }
                          const [min, max] = bands[bucket.value]
                          setFilters((prev) => ({
                            ...prev,
                            min_price: min,
                            max_price: max,
                          }))
                        }}
                        className="flex w-full items-center justify-between text-xs text-gray-600 hover:text-primary disabled:text-gray-300"
                      >
                        <span>{t(`priceBands.${bucket.value}`)}</span>
                        <span>{bucket.count}</span>
                      </button>
                    ))}
                  </div>
                )}
              </FacetSection>

              {facets?.condition?.length > 0 && (
                <FacetSection title={t('condition')}>
                  <select
                    value={filters.condition}
                    onChange={(event) =>
                      updateFilter('condition', event.target.value)
                    }
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                  >
                    <option value="">{t('anyCondition')}</option>
                    {facets.condition.map((row) => (
                      <option key={row.value} value={row.value}>
                        {row.label} ({row.count})
                      </option>
                    ))}
                  </select>
                </FacetSection>
              )}

              <FacetSection title={t('sellerType')}>
                <select
                  value={filters.seller_type}
                  onChange={(event) =>
                    updateFilter('seller_type', event.target.value)
                  }
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  <option value="">{t('anySeller')}</option>
                  <option value="store">{t('sellerStore')}</option>
                  <option value="individual">{t('sellerIndividual')}</option>
                </select>
              </FacetSection>

              <FacetSection title={t('posted')}>
                <select
                  value={filters.posted}
                  onChange={(event) =>
                    updateFilter('posted', event.target.value)
                  }
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  <option value="">{t('anyTime')}</option>
                  <option value="today">{t('postedToday')}</option>
                  <option value="7d">{t('posted7d')}</option>
                  <option value="30d">{t('posted30d')}</option>
                </select>
              </FacetSection>

              <div className="space-y-2">
                <FacetCheckbox
                  label={t('verifiedOnly')}
                  checked={filters.verified === 'true'}
                  onChange={() => toggleBoolean('verified')}
                  count={countFor(facets?.verified, 'true')}
                />
                <FacetCheckbox
                  label={t('withPhotos')}
                  checked={filters.with_photos === 'true'}
                  onChange={() => toggleBoolean('with_photos')}
                  count={countFor(facets?.photos, 'true')}
                />
                <FacetCheckbox
                  label={t('inStockOnly')}
                  checked={filters.in_stock === 'true'}
                  onChange={() => toggleBoolean('in_stock')}
                />
              </div>

              {facets?.attributes &&
                Object.entries(facets.attributes).map(([key, facet]) => (
                  <FacetSection key={key} title={facet.label}>
                    <select
                      value={filters.attributes[key] ?? ''}
                      onChange={(event) =>
                        setFilters((prev) => ({
                          ...prev,
                          attributes: {
                            ...prev.attributes,
                            [key]: event.target.value,
                          },
                        }))
                      }
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                    >
                      <option value="">{t('anyValue')}</option>
                      {facet.values.map((value) => (
                        <option key={value.value} value={value.value}>
                          {value.label} ({value.count})
                        </option>
                      ))}
                    </select>
                  </FacetSection>
                ))}
            </div>
          </aside>

          <section className="lg:col-span-3">
            {loading ? (
              <SkeletonLoader variant="product" count={6} />
            ) : products.length > 0 ? (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5">
                  {products.map((product, index) => (
                    <ProductCard
                      key={product.id}
                      product={product}
                      index={index}
                    />
                  ))}
                </div>
                {next && (
                  <div className="text-center mt-8">
                    <button
                      type="button"
                      onClick={loadMore}
                      disabled={loadingMore}
                      className="btn-secondary inline-flex items-center gap-2"
                    >
                      {loadingMore ? t('loadingMore') : t('loadMore')}
                      <ArrowRight className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div className="bg-white border border-gray-100 rounded-lg shadow-sm p-8 text-center">
                <div className="inline-flex p-4 bg-gray-100 rounded-full mb-4">
                  <Search className="h-10 w-10 text-gray-400" />
                </div>
                <h2 className="text-2xl font-bold text-gray-900 mb-2">
                  {t('empty.title')}
                </h2>
                <p className="text-gray-600 mb-5">{t('empty.subtitle')}</p>

                {meta?.did_you_mean && (
                  <button
                    type="button"
                    onClick={() => {
                      setQInput(meta.did_you_mean)
                      updateFilter('q', meta.did_you_mean)
                    }}
                    className="inline-flex items-center gap-2 mb-5 text-primary font-medium hover:underline"
                  >
                    <Sparkles className="h-4 w-4" />
                    {t('didYouMean', { term: meta.did_you_mean })}
                  </button>
                )}

                {meta?.relaxations?.length > 0 && (
                  <div className="mb-5">
                    <p className="text-sm font-medium text-gray-700 mb-2">
                      {t('empty.relax')}
                    </p>
                    <div className="flex flex-wrap justify-center gap-2">
                      {meta.relaxations.map((row) => (
                        <button
                          key={`${row.param}:${row.value}`}
                          type="button"
                          onClick={() => removeRelaxation(row.param)}
                          className="text-sm bg-gray-100 hover:bg-gray-200 rounded-full px-3 py-1"
                        >
                          {t('empty.removeFilter', {
                            filter: filterLabel(row.param, t),
                            count: row.count,
                          })}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {meta?.nearby_wilayas?.length > 0 && (
                  <div className="mb-5">
                    <p className="text-sm font-medium text-gray-700 mb-2 flex items-center justify-center gap-1">
                      <MapPin className="h-4 w-4" />
                      {t('empty.nearby')}
                    </p>
                    <div className="flex flex-wrap justify-center gap-2">
                      {meta.nearby_wilayas.map((row) => (
                        <button
                          key={row.value}
                          type="button"
                          onClick={() => updateFilter('wilaya', row.value)}
                          className="text-sm bg-primary/10 text-primary hover:bg-primary/20 rounded-full px-3 py-1"
                        >
                          {row.label} ({row.count})
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <button
                  type="button"
                  onClick={clearFilters}
                  className="btn-primary inline-flex items-center gap-2"
                >
                  {t('clearFilters')}
                </button>
              </div>
            )}
          </section>
        </div>
      </motion.div>

      {saveOpen && (
        <SaveSearchDialog
          user={user}
          params={buildParams(filters)}
          onClose={() => setSaveOpen(false)}
          t={t}
        />
      )}
    </div>
  )
}

function FacetSection({ title, children }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
        {title}
      </h3>
      {children}
    </div>
  )
}

function FacetCheckbox({ label, checked, onChange, count }) {
  return (
    <label className="flex items-center justify-between gap-2 text-sm text-gray-700 cursor-pointer">
      <span className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={checked}
          onChange={onChange}
          className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
        />
        {label}
      </span>
      {count != null && <span className="text-xs text-gray-400">{count}</span>}
    </label>
  )
}

function countFor(rows, value) {
  return rows?.find((row) => row.value === value)?.count
}

function filterLabel(param, t) {
  if (param === 'q') return t('empty.labels.q')
  if (param === 'min_price' || param === 'max_price') return t('price')
  if (param === 'with_photos') return t('withPhotos')
  if (param === 'seller_type') return t('sellerType')
  if (param === 'in_stock') return t('inStockOnly')
  if (param === 'posted') return t('posted')
  if (param === 'verified') return t('verifiedOnly')
  if (param.startsWith('attr_')) return param.slice(5).replace(/_/g, ' ')
  return t(`empty.labels.${param}`)
}

function SaveSearchDialog({ user, params, onClose, t }) {
  const [name, setName] = useState('')
  const [frequency, setFrequency] = useState('DAILY')
  const [notifyEmail, setNotifyEmail] = useState(true)
  const [notifySms, setNotifySms] = useState(false)
  const [notifyWhatsapp, setNotifyWhatsapp] = useState(false)
  const [saving, setSaving] = useState(false)
  const hasPhone = Boolean(user?.phone_number)

  const submit = async (event) => {
    event.preventDefault()
    if (!notifyEmail && !notifySms && !notifyWhatsapp) {
      toast.error(t('saved.chooseChannel'))
      return
    }
    setSaving(true)
    try {
      await searchAPI.saveSearch({
        name: name.trim(),
        params,
        frequency,
        notify_email: notifyEmail,
        notify_sms: notifySms,
        notify_whatsapp: notifyWhatsapp,
      })
      toast.success(t('saved.saved'))
      onClose()
    } catch (error) {
      toast.error(error?.response?.data?.message || t('saved.saveError'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 p-4"
      role="presentation"
      onClick={onClose}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-label={t('saved.title')}
        onClick={(event) => event.stopPropagation()}
        onSubmit={submit}
        className="w-full max-w-md bg-white rounded-xl shadow-2xl p-6"
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900">
              {t('saved.title')}
            </h2>
            <p className="text-sm text-gray-500 mt-1">{t('saved.subtitle')}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('saved.close')}
            className="text-gray-400 hover:text-gray-700"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <label
          htmlFor="saved-search-name"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          {t('saved.name')}
        </label>
        <input
          id="saved-search-name"
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t('saved.namePlaceholder')}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 mb-4"
        />

        <fieldset className="mb-4">
          <legend className="text-sm font-medium text-gray-700 mb-2">
            {t('saved.frequency')}
          </legend>
          <div className="flex gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="frequency"
                value="INSTANT"
                checked={frequency === 'INSTANT'}
                onChange={(event) => setFrequency(event.target.value)}
              />
              {t('saved.instant')}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="frequency"
                value="DAILY"
                checked={frequency === 'DAILY'}
                onChange={(event) => setFrequency(event.target.value)}
              />
              {t('saved.daily')}
            </label>
          </div>
        </fieldset>

        <fieldset className="mb-5">
          <legend className="text-sm font-medium text-gray-700 mb-2">
            {t('saved.channels')}
          </legend>
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={notifyEmail}
                onChange={(event) => setNotifyEmail(event.target.checked)}
              />
              {t('saved.email')}
            </label>
            <label
              className={`flex items-center gap-2 text-sm ${
                hasPhone ? '' : 'text-gray-400'
              }`}
            >
              <input
                type="checkbox"
                checked={notifySms}
                disabled={!hasPhone}
                onChange={(event) => setNotifySms(event.target.checked)}
              />
              {t('saved.sms')}
            </label>
            <label
              className={`flex items-center gap-2 text-sm ${
                hasPhone ? '' : 'text-gray-400'
              }`}
            >
              <input
                type="checkbox"
                checked={notifyWhatsapp}
                disabled={!hasPhone}
                onChange={(event) => setNotifyWhatsapp(event.target.checked)}
              />
              {t('saved.whatsapp')}
            </label>
            {!hasPhone && (
              <p className="text-xs text-gray-500">{t('saved.addPhone')}</p>
            )}
          </div>
        </fieldset>

        <button
          type="submit"
          disabled={saving}
          className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-60"
        >
          <Bookmark className="h-4 w-4" />
          {saving ? t('saved.saving') : t('saved.saveButton')}
        </button>
      </form>
    </div>
  )
}
