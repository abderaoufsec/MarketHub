'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { storesAPI, productsAPI } from '../../../lib/api'
import Link from 'next/link'
import ProductCard from '../../../components/product/ProductCard'
import { Store, MapPin, Calendar, Package, ArrowLeft } from 'lucide-react'

export default function StoreDetailPage() {
  const params = useParams()
  const [store, setStore] = useState(null)
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [productsLoading, setProductsLoading] = useState(true)

  useEffect(() => {
    if (params.slug) {
      fetchStoreDetails()
      fetchStoreProducts()
    }
  }, [params.slug])

  const fetchStoreDetails = async () => {
    try {
      setLoading(true)
      const response = await storesAPI.get(params.slug)
      setStore(response.data)
    } catch (error) {
      console.error('Error fetching store:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchStoreProducts = async () => {
    try {
      setProductsLoading(true)
      // Fetch products filtered by store slug
      const response = await productsAPI.list({ store: params.slug })
      setProducts(response.data.results || response.data || [])
    } catch (error) {
      console.error('Error fetching products:', error)
    } finally {
      setProductsLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  if (!store) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8 text-center">
        <Store className="h-16 w-16 text-gray-400 mx-auto mb-4" />
        <p className="text-gray-500 text-lg mb-4">Store not found</p>
        <Link href="/stores" className="text-primary hover:text-secondary">
          Browse All Stores
        </Link>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Back Button */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        <Link
          href="/stores"
          className="inline-flex items-center text-gray-600 hover:text-primary"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Stores
        </Link>
      </div>

      {/* Store Banner */}
      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Banner Image */}
          <div className="h-48 md:h-64 bg-gradient-to-r from-primary to-secondary rounded-lg overflow-hidden -mx-4 sm:mx-0 sm:mt-6 relative">
            {store.banner_image_url ? (
              <img
                src={store.banner_image_url}
                alt={store.store_name}
                className="w-full h-full object-cover"
                onError={(e) => {
                  e.target.style.display = 'none'
                }}
              />
            ) : (
              <div className="flex items-center justify-center h-full">
                <Store className="h-20 w-20 text-white opacity-30" />
              </div>
            )}
          </div>

          {/* Store Info */}
          <div className="py-6">
            <div className="flex flex-col md:flex-row gap-6">
              {/* Logo */}
              <div className="flex-shrink-0">
                {store.logo_url ? (
                  <img
                    src={store.logo_url}
                    alt={`${store.store_name} logo`}
                    className="h-24 w-24 rounded-full object-cover border-4 border-white shadow-lg"
                    onError={(e) => {
                      e.target.src = '/placeholder-store.jpg'
                    }}
                  />
                ) : (
                  <div className="h-24 w-24 rounded-full bg-primary text-white flex items-center justify-center font-bold text-3xl border-4 border-white shadow-lg">
                    {store.store_name.charAt(0).toUpperCase()}
                  </div>
                )}
              </div>

              {/* Store Details */}
              <div className="flex-1">
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                  <div>
                    <h1 className="text-3xl font-bold text-gray-900 mb-2">
                      {store.store_name}
                    </h1>
                    {store.category && (
                      <span className="inline-block bg-blue-100 text-primary px-3 py-1 rounded-full text-sm font-medium">
                        {store.category}
                      </span>
                    )}
                  </div>
                  {store.is_active && (
                    <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800">
                      Active Store
                    </span>
                  )}
                </div>

                {store.description && (
                  <p className="text-gray-600 mt-4 max-w-3xl">
                    {store.description}
                  </p>
                )}

                {/* Store Meta */}
                <div className="flex flex-wrap gap-4 mt-4 text-sm text-gray-600">
                  {store.created_at && (
                    <div className="flex items-center gap-1">
                      <Calendar className="h-4 w-4" />
                      <span>
                        Joined{' '}
                        {new Date(store.created_at).toLocaleDateString(
                          'en-US',
                          {
                            year: 'numeric',
                            month: 'long',
                          }
                        )}
                      </span>
                    </div>
                  )}
                  <div className="flex items-center gap-1">
                    <Package className="h-4 w-4" />
                    <span>{products.length} Products</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Products Section */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900">Products</h2>
          <p className="text-gray-600 mt-1">
            Browse all products from {store.store_name}
          </p>
        </div>

        {productsLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="bg-white border border-gray-200 rounded-lg p-4 animate-pulse"
              >
                <div className="bg-gray-300 h-48 rounded-lg mb-4"></div>
                <div className="bg-gray-300 h-4 rounded w-3/4 mb-2"></div>
                <div className="bg-gray-300 h-4 rounded w-1/2"></div>
              </div>
            ))}
          </div>
        ) : products.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-lg border border-gray-200">
            <Package className="h-16 w-16 text-gray-400 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-gray-900 mb-2">
              No products yet
            </h3>
            <p className="text-gray-600">
              This store hasn't listed any products yet. Check back later!
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {products.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
