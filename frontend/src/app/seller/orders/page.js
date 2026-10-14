'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../../../context/AuthContext'
import { ordersAPI } from '../../../lib/api'
import { usePrice } from '../../../lib/currency'
import { useTranslations } from 'next-intl'
import { ShoppingBag, Calendar, Package, DollarSign } from 'lucide-react'

const ORDER_STATUS_OPTIONS = [
  'PENDING',
  'PROCESSING',
  'SHIPPED',
  'DELIVERED',
  'CANCELLED',
]

export default function SellerOrdersPage() {
  const router = useRouter()
  const t = useTranslations('seller')
  const price = usePrice()
  const { isAuthenticated, isSeller, loading: authLoading } = useAuth()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    if (!authLoading && (!isAuthenticated || !isSeller)) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, isSeller, router])

  useEffect(() => {
    if (isAuthenticated && isSeller) {
      fetchOrders()
    }
  }, [isAuthenticated, isSeller])

  const fetchOrders = async () => {
    try {
      setLoading(true)
      const response = await ordersAPI.sellerList()
      setOrders(response.data.results || response.data || [])
    } catch (error) {
      console.error('Error fetching orders:', error)
    } finally {
      setLoading(false)
    }
  }

  const filteredOrders = orders.filter(
    (order) => filter === 'all' || order.order_status === filter
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
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">
          {t('orders.title')}
        </h1>
        <p className="text-gray-600 mt-1">{t('orders.subtitle')}</p>
      </div>

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label={t('orders.filterLabel')}
          className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
        >
          <option value="all">{t('orders.filterAll')}</option>
          {ORDER_STATUS_OPTIONS.map((status) => (
            <option key={status} value={status}>
              {t(`orders.statuses.${status.toLowerCase()}`)}
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white border border-gray-200 rounded-lg p-6 animate-pulse"
            >
              <div className="h-6 bg-gray-300 rounded w-1/4 mb-4"></div>
              <div className="h-4 bg-gray-300 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      ) : filteredOrders.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-lg border border-gray-200">
          <ShoppingBag className="h-16 w-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-gray-900 mb-2">
            {t('orders.empty.title')}
          </h3>
          <p className="text-gray-600">{t('orders.empty.body')}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredOrders.map((order) => (
            <div
              key={order.id}
              className="bg-white border border-gray-200 rounded-lg p-6"
            >
              <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-4">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">
                    {t('orders.number', { id: order.id })}
                  </h3>
                  <div className="flex flex-wrap gap-4 text-sm text-gray-600">
                    <div className="flex items-center gap-1">
                      <Calendar className="h-4 w-4" />
                      <span>
                        {new Date(order.order_date).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Package className="h-4 w-4" />
                      <span>
                        {t('orders.itemsCount', {
                          count: order.items?.length || 0,
                        })}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <DollarSign className="h-4 w-4" />
                      <span className="font-semibold">
                        {price(order.total_amount)}
                      </span>
                    </div>
                  </div>
                </div>
                <div>
                  <span
                    className={`px-4 py-2 rounded-full text-sm font-medium ${
                      order.order_status === 'DELIVERED'
                        ? 'bg-green-100 text-green-800'
                        : order.order_status === 'CANCELLED'
                          ? 'bg-red-100 text-red-800'
                          : order.order_status === 'SHIPPED'
                            ? 'bg-purple-100 text-purple-800'
                            : order.order_status === 'PROCESSING'
                              ? 'bg-blue-100 text-blue-800'
                              : 'bg-yellow-100 text-yellow-800'
                    }`}
                  >
                    {order.order_status_label || order.order_status}
                  </span>
                </div>
              </div>

              {order.items && order.items.length > 0 && (
                <div className="border-t pt-4">
                  <h4 className="text-sm font-medium text-gray-700 mb-2">
                    {t('orders.itemsTitle')}
                  </h4>
                  <div className="space-y-2">
                    {order.items.map((item, idx) => (
                      <div key={idx} className="flex justify-between text-sm">
                        <span className="text-gray-700">
                          {item.product?.name || t('orders.unknownProduct')} ×{' '}
                          {item.quantity}
                        </span>
                        <span className="font-medium">
                          {price(item.unit_price_at_purchase)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {order.shipping_address && (
                <div className="border-t pt-4 mt-4">
                  <h4 className="text-sm font-medium text-gray-700 mb-2">
                    {t('orders.shippingTitle')}
                  </h4>
                  <p className="text-sm text-gray-600">
                    {order.shipping_address.address_line1},{' '}
                    {order.shipping_address.city},{' '}
                    {order.shipping_address.state_province}{' '}
                    {order.shipping_address.postal_code}
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
