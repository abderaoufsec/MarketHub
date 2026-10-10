'use client'

import { useState, useEffect } from 'react'
import { storesAPI } from '../../lib/api'
import Link from 'next/link'
import { Store, Search, ChevronRight, Package } from 'lucide-react'

export default function StoresPage() {
  const [stores, setStores] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [filteredStores, setFilteredStores] = useState([])

  useEffect(() => {
    fetchStores()
  }, [])

  useEffect(() => {
    if (searchTerm) {
      const filtered = stores.filter(
        (store) =>
          store.store_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          store.category?.toLowerCase().includes(searchTerm.toLowerCase()) ||
          store.description?.toLowerCase().includes(searchTerm.toLowerCase())
      )
      setFilteredStores(filtered)
    } else {
      setFilteredStores(stores)
    }
  }, [searchTerm, stores])

  const fetchStores = async () => {
    try {
      setLoading(true)
      const response = await storesAPI.list()
      const storesData = response.data.results || response.data || []
      setStores(storesData)
      setFilteredStores(storesData)
    } catch (error) {
      console.error('Error fetching stores:', error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Browse Stores</h1>
        <p className="text-gray-600">
          Discover unique products from verified sellers
        </p>
      </div>

      {/* Search */}
      <div className="mb-8">
        <div className="relative max-w-xl">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search stores by name, category, or description..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
          />
        </div>
      </div>

      {/* Loading State */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div
              key={i}
              className="bg-white border border-gray-200 rounded-lg p-6 animate-pulse"
            >
              <div className="h-6 bg-gray-300 rounded w-3/4 mb-3"></div>
              <div className="h-4 bg-gray-300 rounded w-1/2 mb-4"></div>
              <div className="h-4 bg-gray-300 rounded w-full mb-2"></div>
              <div className="h-4 bg-gray-300 rounded w-2/3"></div>
            </div>
          ))}
        </div>
      ) : filteredStores.length === 0 ? (
        <div className="text-center py-16">
          <Store className="h-16 w-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-gray-900 mb-2">
            {searchTerm ? 'No stores found' : 'No stores available'}
          </h3>
          <p className="text-gray-600 mb-6">
            {searchTerm
              ? 'Try adjusting your search terms'
              : 'Check back later for new stores'}
          </p>
          {searchTerm && (
            <button onClick={() => setSearchTerm('')} className="btn-primary">
              Clear Search
            </button>
          )}
        </div>
      ) : (
        <>
          {/* Results Count */}
          <div className="mb-4 text-sm text-gray-600">
            Showing {filteredStores.length}{' '}
            {filteredStores.length === 1 ? 'store' : 'stores'}
          </div>

          {/* Stores Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredStores.map((store) => (
              <Link
                key={store.id}
                href={`/stores/${store.store_slug}`}
                className="bg-white border border-gray-200 rounded-lg overflow-hidden hover:shadow-lg transition-shadow group"
              >
                {/* Store Banner */}
                <div className="h-32 bg-gradient-to-r from-primary to-secondary relative overflow-hidden">
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
                      <Store className="h-12 w-12 text-white opacity-50" />
                    </div>
                  )}
                </div>

                {/* Store Info */}
                <div className="p-6">
                  {/* Logo */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      {store.logo_url ? (
                        <img
                          src={store.logo_url}
                          alt={`${store.store_name} logo`}
                          className="h-12 w-12 rounded-full object-cover border-2 border-white shadow-md"
                          onError={(e) => {
                            e.target.src = '/placeholder-store.jpg'
                          }}
                        />
                      ) : (
                        <div className="h-12 w-12 rounded-full bg-primary text-white flex items-center justify-center font-bold text-lg">
                          {store.store_name.charAt(0).toUpperCase()}
                        </div>
                      )}
                      <div>
                        <h3 className="text-lg font-semibold text-gray-900 group-hover:text-primary transition-colors">
                          {store.store_name}
                        </h3>
                        {store.category && (
                          <span className="text-xs text-gray-600 bg-gray-100 px-2 py-1 rounded">
                            {store.category}
                          </span>
                        )}
                      </div>
                    </div>
                    <ChevronRight className="h-5 w-5 text-gray-400 group-hover:text-primary transition-colors flex-shrink-0" />
                  </div>

                  {/* Description */}
                  <p className="text-sm text-gray-600 line-clamp-2 mb-4">
                    {store.description || 'A trusted seller on MarketHub'}
                  </p>

                  {/* Stats */}
                  <div className="flex items-center justify-between text-sm text-gray-600 pt-4 border-t border-gray-200">
                    <div className="flex items-center gap-1">
                      <Package className="h-4 w-4" />
                      <span>Products</span>
                    </div>
                    {store.is_active ? (
                      <span className="text-green-600 font-medium">Active</span>
                    ) : (
                      <span className="text-gray-400">Inactive</span>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
