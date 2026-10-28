'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../../../context/AuthContext'
import { productsAPI } from '../../../lib/api'
import { apiErrorMessage } from '../../../lib/errors'
import { usePrice } from '../../../lib/currency'
import { useTranslations } from 'next-intl'
import Link from 'next/link'
import toast from 'react-hot-toast'
import {
  Package,
  Plus,
  Edit,
  Trash2,
  Search,
  Send,
  BadgeCheck,
  RotateCcw,
  Archive,
  Undo2,
} from 'lucide-react'

/**
 * The seller's listings (Phase 13): one page for store SKUs *and*
 * classifieds, tabbed by lifecycle status — the tabs are a server-side
 * `?status=` filter, so "Drafts" stays true at 500 rows.
 *
 * Lifecycle actions come straight from the state machine: only the ones
 * `apps/products/lifecycle.py` allows for a row's current status are
 * rendered, and the row moves tabs after the action because the state it was
 * in is over.
 */

const STATUS_TABS = ['all', 'ACTIVE', 'DRAFT', 'SOLD', 'EXPIRED', 'ARCHIVED']

const STATUS_BADGE = {
  ACTIVE: 'bg-green-100 text-green-800',
  DRAFT: 'bg-gray-100 text-gray-700',
  PENDING_REVIEW: 'bg-yellow-100 text-yellow-800',
  SOLD: 'bg-blue-100 text-blue-800',
  EXPIRED: 'bg-orange-100 text-orange-800',
  ARCHIVED: 'bg-gray-100 text-gray-500',
  REJECTED: 'bg-red-100 text-red-800',
}

/** What a listing in this status may do next (mirrors the backend map). */
function actionsFor(status) {
  switch (status) {
    case 'DRAFT':
      return ['publish']
    case 'ACTIVE':
      return ['mark_sold', 'archive']
    case 'PENDING_REVIEW':
      return ['withdraw']
    case 'SOLD':
      return ['relist']
    case 'EXPIRED':
      return ['renew']
    case 'ARCHIVED':
      return ['restore']
    default:
      return []
  }
}

export default function SellerProductsPage() {
  const router = useRouter()
  const t = useTranslations('seller')
  const price = usePrice()
  const { isAuthenticated, isSeller, loading: authLoading } = useAuth()
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [status, setStatus] = useState('all')
  const [quota, setQuota] = useState(null)
  const [actingOn, setActingOn] = useState(null)

  useEffect(() => {
    if (!authLoading && (!isAuthenticated || !isSeller)) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, isSeller, router])

  const fetchProducts = useCallback(
    async (statusFilter) => {
      try {
        setLoading(true)
        const response = await productsAPI.sellerList(
          statusFilter && statusFilter !== 'all'
            ? { status: statusFilter }
            : undefined
        )
        setProducts(response.data.results || response.data || [])
      } catch (error) {
        console.error('Error fetching products:', error)
        toast.error(apiErrorMessage(error, t('products.loadError')))
      } finally {
        setLoading(false)
      }
    },
    [t]
  )

  useEffect(() => {
    if (isAuthenticated && isSeller) {
      fetchProducts(status)
      productsAPI
        .quota()
        .then((response) => setQuota(response.data))
        .catch(() => {})
    }
  }, [isAuthenticated, isSeller, status, fetchProducts])

  const handleDelete = async (id) => {
    if (confirm(t('products.deleteConfirm'))) {
      try {
        await productsAPI.delete(id)
        setProducts(products.filter((p) => p.id !== id))
      } catch (error) {
        console.error('Error deleting product:', error)
        alert(t('products.deleteError'))
      }
    }
  }

  const handleLifecycle = async (product, action) => {
    const confirmKey = {
      mark_sold: 'confirmMarkSold',
      archive: 'confirmArchive',
    }[action]
    if (confirmKey && !confirm(t(`products.lifecycle.${confirmKey}`))) return
    setActingOn(product.id)
    try {
      await productsAPI.lifecycle(product.id, action)
      toast.success(t(`products.lifecycle.${action}Done`))
      // The row's status just changed — it belongs to another tab now.
      fetchProducts(status)
      productsAPI
        .quota()
        .then((response) => setQuota(response.data))
        .catch(() => {})
    } catch (error) {
      toast.error(apiErrorMessage(error, t('products.lifecycle.failed')))
    } finally {
      setActingOn(null)
    }
  }

  const filteredProducts = products.filter((product) =>
    (product.name || '').toLowerCase().includes(searchTerm.toLowerCase())
  )

  if (authLoading || !isAuthenticated || !isSeller) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">
            {t('products.heading')}
          </h1>
          <p className="text-gray-600 mt-1">{t('products.subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <Link href="/post" className="btn-secondary flex items-center gap-2">
            <Plus className="h-5 w-5" />
            {t('products.postAd')}
          </Link>
          <Link
            href="/seller/products/create"
            className="btn-primary flex items-center gap-2"
          >
            <Plus className="h-5 w-5" />
            {t('products.addNew')}
          </Link>
        </div>
      </div>

      {/* Quota strip — where every publish attempt starts and ends. */}
      {quota && quota.listing_quota != null && (
        <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 mb-6 text-sm text-gray-600">
          {t('products.quotaLine', {
            used: quota.active_listings,
            limit: quota.listing_quota,
            drafts: quota.drafts,
            draftLimit: quota.draft_limit,
          })}
        </div>
      )}

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        {/* Status tabs — server-side filter, one honest count each. */}
        <div className="flex flex-wrap gap-2 mb-4">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setStatus(tab)}
              className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                status === tab
                  ? 'border-primary text-primary bg-primary/5 font-medium'
                  : 'border-gray-300 text-gray-600 hover:border-primary'
              }`}
            >
              {tab === 'all'
                ? t('products.tabs.all')
                : t(`products.tabs.${tab}`)}
            </button>
          ))}
        </div>
        <div className="relative">
          <Search className="absolute start-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
          <input
            type="text"
            placeholder={t('products.searchPlaceholder')}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full ps-10 pe-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
          />
        </div>
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white border border-gray-200 rounded-lg p-6 animate-pulse"
            >
              <div className="h-6 bg-gray-300 rounded w-1/3 mb-4"></div>
              <div className="h-4 bg-gray-300 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      ) : filteredProducts.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-lg border border-gray-200">
          <Package className="h-16 w-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-gray-900 mb-2">
            {searchTerm || status !== 'all'
              ? t('products.emptyState.noResults')
              : t('products.emptyState.noneYet')}
          </h3>
          <p className="text-gray-600 mb-6">
            {searchTerm || status !== 'all'
              ? t('products.emptyState.noResultsHint')
              : t('products.emptyState.startHint')}
          </p>
          {!searchTerm && status === 'all' && (
            <div className="flex justify-center gap-2">
              <Link href="/post" className="btn-secondary inline-block">
                {t('products.emptyState.postAdFirst')}
              </Link>
              <Link
                href="/seller/products/create"
                className="btn-primary inline-block"
              >
                {t('products.emptyState.addFirst')}
              </Link>
            </div>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {filteredProducts.map((product) => (
            <div
              key={product.id}
              className="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow"
            >
              <div className="flex flex-col sm:flex-row gap-4">
                <div className="h-24 w-24 bg-gray-100 rounded-lg flex-shrink-0 overflow-hidden">
                  {(product.images?.[0] || product.primary_image) && (
                    <img
                      src={
                        product.images?.[0]?.image_url || product.primary_image
                      }
                      alt={product.name}
                      className="h-full w-full object-cover"
                      onError={(e) => {
                        e.target.src = '/placeholder-product.jpg'
                      }}
                    />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-4 mb-2">
                    <div className="flex-1 min-w-0">
                      <h3 className="text-lg font-semibold text-gray-900 truncate">
                        {product.name}
                      </h3>
                      <p className="text-gray-600 text-sm line-clamp-2">
                        {product.description}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      {product.status_label && (
                        <span
                          className={`px-3 py-1 rounded-full text-xs font-medium ${
                            STATUS_BADGE[product.status] ||
                            'bg-gray-100 text-gray-700'
                          }`}
                        >
                          {product.status_label}
                        </span>
                      )}
                      {product.listing_type_label && (
                        <span className="px-3 py-1 rounded-full text-xs font-medium bg-gray-50 text-gray-600 border border-gray-200">
                          {product.listing_type_label}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-4 text-sm text-gray-600 mb-4">
                    <span>
                      {t('products.card.price')}{' '}
                      <strong className="text-gray-900">
                        {product.base_price != null
                          ? price(product.base_price)
                          : t('products.card.priceOnRequest')}
                      </strong>
                    </span>
                    {product.category && (
                      <span>
                        {t('products.card.category')}{' '}
                        <strong className="text-gray-900">
                          {product.category.name || product.category}
                        </strong>
                      </span>
                    )}
                    {product.wilaya_name && (
                      <span>
                        {t('products.card.location')}{' '}
                        <strong className="text-gray-900">
                          {product.wilaya_name}
                        </strong>
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2 items-center">
                    <Link
                      href={product.canonical_path || `/products/${product.id}`}
                      className="text-sm text-gray-600 hover:text-primary"
                    >
                      {t('products.card.viewPublic')}
                    </Link>
                    <span className="text-gray-300">|</span>
                    <Link
                      href={`/seller/products/${product.id}/edit`}
                      className="text-sm text-primary hover:text-secondary flex items-center gap-1"
                    >
                      <Edit className="h-4 w-4" />
                      {t('products.card.edit')}
                    </Link>
                    {actionsFor(product.status).map((action) => {
                      const icons = {
                        publish: Send,
                        mark_sold: BadgeCheck,
                        renew: RotateCcw,
                        relist: RotateCcw,
                        archive: Archive,
                        restore: Undo2,
                        withdraw: Undo2,
                      }
                      const Icon = icons[action] || Send
                      return (
                        <span key={action}>
                          <span className="text-gray-300">|</span>{' '}
                          <button
                            onClick={() => handleLifecycle(product, action)}
                            disabled={actingOn === product.id}
                            className="text-sm text-primary hover:text-secondary flex items-center gap-1 disabled:opacity-50"
                          >
                            <Icon className="h-4 w-4" />
                            {t(`products.lifecycle.${action}`)}
                          </button>
                        </span>
                      )
                    })}
                    <span className="text-gray-300">|</span>
                    <button
                      onClick={() => handleDelete(product.id)}
                      className="text-sm text-red-600 hover:text-red-700 flex items-center gap-1"
                    >
                      <Trash2 className="h-4 w-4" />
                      {t('products.card.delete')}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
