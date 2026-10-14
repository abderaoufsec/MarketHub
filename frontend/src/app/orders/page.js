'use client'

import { useState, useEffect } from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { useAuth } from '../../context/AuthContext'
import { ordersAPI } from '../../lib/api'
import { usePrice } from '../../lib/currency'
import { intlLocale } from '../../i18n/config'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Package,
  Calendar,
  DollarSign,
  ChevronRight,
  ShoppingBag,
} from 'lucide-react'

// Colour per status *value*; the words themselves come from the backend's
// translated `order_status_label` (Phase 11) — never from this file.
const ORDER_STATUS_COLORS = {
  PENDING: 'bg-yellow-100 text-yellow-800',
  PROCESSING: 'bg-blue-100 text-blue-800',
  SHIPPED: 'bg-purple-100 text-purple-800',
  DELIVERED: 'bg-green-100 text-green-800',
  CANCELLED: 'bg-red-100 text-red-800',
}

export default function OrdersPage() {
  const t = useTranslations('orders')
  const locale = useLocale()
  const { isAuthenticated, user, loading: authLoading } = useAuth()
  const router = useRouter()
  // Locale-aware DZD formatter (Phase 11) — dinars, never a `$`.
  const price = usePrice()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, router])

  useEffect(() => {
    if (isAuthenticated) {
      fetchOrders()
    }
  }, [isAuthenticated])

  const fetchOrders = async () => {
    try {
      setLoading(true)
      const response = await ordersAPI.list()
      setOrders(response.data.results || response.data || [])
    } catch (error) {
      console.error('Error fetching orders:', error)
    } finally {
      setLoading(false)
    }
  }

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">{t('title')}</h1>
        <p className="text-gray-600 mt-2">{t('subtitle')}</p>
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white border border-gray-200 rounded-lg p-6 animate-pulse"
            >
              <div className="h-6 bg-gray-300 rounded w-1/4 mb-4"></div>
              <div className="h-4 bg-gray-300 rounded w-1/2 mb-2"></div>
              <div className="h-4 bg-gray-300 rounded w-1/3"></div>
            </div>
          ))}
        </div>
      ) : orders.length === 0 ? (
        <div className="text-center py-16">
          <ShoppingBag className="h-16 w-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-gray-900 mb-2">
            {t('empty.title')}
          </h3>
          <p className="text-gray-600 mb-6">{t('empty.text')}</p>
          <Link href="/products" className="btn-primary inline-block">
            {t('empty.browseProducts')}
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {orders.map((order) => (
            <Link
              key={order.id}
              href={`/orders/${order.id}`}
              className="block bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow"
            >
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-lg font-semibold text-gray-900">
                      {t('orderNumber', { id: order.id })}
                    </h3>
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-medium ${
                        ORDER_STATUS_COLORS[order.order_status] ||
                        'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {/* Translated server-side (Phase 11); raw value is the
                          only fallback so a new status is still visible. */}
                      {order.order_status_label || order.order_status}
                    </span>
                  </div>

                  <div className="flex flex-wrap gap-4 text-sm text-gray-600">
                    <div className="flex items-center gap-1">
                      <Calendar className="h-4 w-4" />
                      <span>
                        {new Date(order.order_date).toLocaleDateString(
                          intlLocale(locale)
                        )}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Package className="h-4 w-4" />
                      <span>
                        {t('itemCount', { count: order.items?.length || 0 })}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <DollarSign className="h-4 w-4" />
                      <span className="font-semibold">
                        {price(order.total_amount)}
                      </span>
                    </div>
                  </div>

                  {order.store_name && (
                    <p className="text-sm text-gray-600 mt-2">
                      {t('soldBy')}{' '}
                      <span className="font-medium">{order.store_name}</span>
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-primary font-medium text-sm">
                    {t('viewDetails')}
                  </span>
                  <ChevronRight className="h-5 w-5 text-primary" />
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
