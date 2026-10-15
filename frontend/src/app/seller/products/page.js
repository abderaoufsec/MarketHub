'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../../../context/AuthContext'
import { productsAPI } from '../../../lib/api'
import { usePrice } from '../../../lib/currency'
import { useTranslations } from 'next-intl'
import Link from 'next/link'
import { Package, Plus, Edit, Trash2, Search } from 'lucide-react'

export default function SellerProductsPage() {
  const router = useRouter()
  const t = useTranslations('seller')
  const price = usePrice()
  const { isAuthenticated, isSeller, loading: authLoading } = useAuth()
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    if (!authLoading && (!isAuthenticated || !isSeller)) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, isSeller, router])

  useEffect(() => {
    if (isAuthenticated && isSeller) {
      fetchProducts()
    }
  }, [isAuthenticated, isSeller])

  const fetchProducts = async () => {
    try {
      setLoading(true)
      const response = await productsAPI.sellerList()
      setProducts(response.data.results || response.data || [])
    } catch (error) {
      console.error('Error fetching products:', error)
    } finally {
      setLoading(false)
    }
  }

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

  const filteredProducts = products.filter((product) => {
    const matchesSearch = product.name
      .toLowerCase()
      .includes(searchTerm.toLowerCase())
    const matchesFilter =
      filter === 'all' ||
      (filter === 'available' && product.is_available) ||
      (filter === 'unavailable' && !product.is_available)
    return matchesSearch && matchesFilter
  })

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
        <Link
          href="/seller/products/create"
          className="btn-primary flex items-center gap-2"
        >
          <Plus className="h-5 w-5" />
          {t('products.addNew')}
        </Link>
      </div>

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute start-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
            <input
              type="text"
              placeholder={t('products.searchPlaceholder')}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full ps-10 pe-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
            />
          </div>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
          >
            <option value="all">{t('products.filters.all')}</option>
            <option value="available">{t('products.filters.available')}</option>
            <option value="unavailable">
              {t('products.filters.outOfStock')}
            </option>
          </select>
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
            {searchTerm
              ? t('products.emptyState.noResults')
              : t('products.emptyState.noneYet')}
          </h3>
          <p className="text-gray-600 mb-6">
            {searchTerm
              ? t('products.emptyState.noResultsHint')
              : t('products.emptyState.startHint')}
          </p>
          {!searchTerm && (
            <Link
              href="/seller/products/create"
              className="btn-primary inline-block"
            >
              {t('products.emptyState.addFirst')}
            </Link>
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
                  {product.images?.[0] && (
                    <img
                      src={product.images[0].image_url}
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
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-medium flex-shrink-0 ${
                        product.is_available
                          ? 'bg-green-100 text-green-800'
                          : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {product.is_available
                        ? t('products.filters.available')
                        : t('products.filters.outOfStock')}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-4 text-sm text-gray-600 mb-4">
                    <span>
                      {t('products.card.price')}{' '}
                      <strong className="text-gray-900">
                        {price(product.base_price)}
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
                  </div>
                  <div className="flex gap-2">
                    <Link
                      href={`/products/${product.id}`}
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
