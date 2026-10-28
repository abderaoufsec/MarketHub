'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useAuth } from '../../../context/AuthContext'
import { ordersAPI } from '../../../lib/api'
import { usePrice } from '../../../lib/currency'
import { intlLocale } from '../../../i18n/config'
import Link from 'next/link'
import {
  Calendar,
  MapPin,
  CreditCard,
  Store,
  ArrowLeft,
  CheckCircle,
} from 'lucide-react'

// Colour (and the timeline emoji) per status *value*; the words themselves
// come from the backend's translated `order_status_label` /
// `payment_status_label` (Phase 11) — never from a client-side English map.
const ORDER_STATUS_COLORS = {
  PENDING: 'bg-yellow-100 text-yellow-800',
  PROCESSING: 'bg-blue-100 text-blue-800',
  SHIPPED: 'bg-purple-100 text-purple-800',
  DELIVERED: 'bg-green-100 text-green-800',
  CANCELLED: 'bg-red-100 text-red-800',
}

const ORDER_STATUS_ICONS = {
  PENDING: '⏳',
  PROCESSING: '⚙️',
  SHIPPED: '🚚',
  DELIVERED: '✅',
  CANCELLED: '❌',
}

const PAYMENT_STATUS_COLORS = {
  PENDING: 'text-yellow-600',
  SUCCESSFUL: 'text-green-600',
  FAILED: 'text-red-600',
}

const TIMELINE_STATUSES = ['PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED']

export default function OrderDetailPage() {
  const params = useParams()
  const router = useRouter()
  const t = useTranslations('orders')
  const locale = useLocale()
  // Locale-aware DZD formatter (Phase 11) — dinars, never a `$`.
  const price = usePrice()
  const { isAuthenticated, loading: authLoading } = useAuth()
  const [order, setOrder] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, router])

  useEffect(() => {
    if (params.id && isAuthenticated) {
      fetchOrderDetails()
    }
  }, [params.id, isAuthenticated])

  const fetchOrderDetails = async () => {
    try {
      setLoading(true)
      const response = await ordersAPI.get(params.id)
      setOrder(response.data)
    } catch (error) {
      console.error('Error fetching order:', error)
    } finally {
      setLoading(false)
    }
  }

  if (authLoading || !isAuthenticated || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  if (!order) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8 text-center">
        <p className="text-gray-500 text-lg">{t('detail.notFound')}</p>
        <Link
          href="/orders"
          className="text-primary hover:text-secondary mt-4 inline-block"
        >
          {t('detail.backToOrders')}
        </Link>
      </div>
    )
  }

  // Phase 11: an address is a street line plus a wilaya and an optional
  // commune, each with a localized name — the free-text city/state/postal
  // trio is gone.
  const shippingAddress = order.shipping_address
  const shippingLocation = [
    shippingAddress?.commune?.name,
    shippingAddress?.wilaya?.name,
  ]
    .filter(Boolean)
    .join(', ')

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Back Button */}
      <Link
        href="/orders"
        className="inline-flex items-center text-gray-600 hover:text-primary mb-6"
      >
        <ArrowLeft className="h-4 w-4 me-2" />
        {t('detail.backToOrders')}
      </Link>

      {/* Order Header */}
      <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {t('orderNumber', { id: order.id })}
            </h1>
            <div className="flex items-center gap-2 text-sm text-gray-600 mt-2">
              <Calendar className="h-4 w-4" />
              <span>
                {t('detail.placedOn', {
                  date: new Date(order.order_date).toLocaleDateString(
                    intlLocale(locale),
                    { year: 'numeric', month: 'long', day: 'numeric' }
                  ),
                })}
              </span>
            </div>
          </div>
          <span
            className={`px-4 py-2 rounded-full text-sm font-medium ${
              ORDER_STATUS_COLORS[order.order_status] ||
              'bg-gray-100 text-gray-800'
            }`}
          >
            {ORDER_STATUS_ICONS[order.order_status]}{' '}
            {/* Translated server-side (Phase 11); raw value is the only
                fallback so a new status is still visible. */}
            {order.order_status_label || order.order_status}
          </span>
        </div>

        {/* Store Info */}
        {order.store_name && (
          <div className="pt-4 border-t border-gray-200">
            {/* Link only when the payload carries a slug — ``order.store`` is
                just the FK id, so a slug-less store must fall back to plain
                text rather than a dead /stores/undefined link. */}
            {order.store_slug ? (
              <Link
                href={`/stores/${order.store_slug}`}
                className="flex items-center gap-2 text-gray-700 hover:text-primary w-fit"
              >
                <Store className="h-5 w-5" />
                <span className="font-medium">{order.store_name}</span>
              </Link>
            ) : (
              <div className="flex items-center gap-2 text-gray-700">
                <Store className="h-5 w-5" />
                <span className="font-medium">{order.store_name}</span>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Order Items */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              {t('detail.items')}
            </h2>
            <div className="space-y-4">
              {order.items &&
                order.items.map((item) => (
                  <div
                    key={item.id}
                    className="flex gap-4 pb-4 border-b border-gray-200 last:border-0"
                  >
                    <div className="h-20 w-20 bg-gray-100 rounded-lg flex-shrink-0">
                      {item.product?.images?.[0] && (
                        <img
                          src={item.product.images[0].image_url}
                          alt={item.product.name}
                          className="h-full w-full object-cover rounded-lg"
                          onError={(e) => {
                            e.target.src = '/placeholder-product.jpg'
                          }}
                        />
                      )}
                    </div>
                    <div className="flex-1">
                      <Link
                        href={`/products/${item.product?.id}`}
                        className="font-medium text-gray-900 hover:text-primary"
                      >
                        {item.product?.name || t('detail.product')}
                      </Link>
                      {item.selected_attributes &&
                        Object.keys(item.selected_attributes).length > 0 && (
                          <div className="text-sm text-gray-600 mt-1">
                            {Object.entries(item.selected_attributes).map(
                              ([key, value]) => (
                                <span key={key} className="me-3">
                                  {key}: {value}
                                </span>
                              )
                            )}
                          </div>
                        )}
                      <div className="text-sm text-gray-600 mt-1">
                        {t('detail.quantity', { count: item.quantity })}
                      </div>
                    </div>
                    <div className="text-end">
                      <div className="font-semibold text-gray-900">
                        {price(item.unit_price_at_purchase)}
                      </div>
                      <div className="text-sm text-gray-600">
                        {t('detail.each')}
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>

          {/* Shipping Address */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <div className="flex items-center gap-2 mb-4">
              <MapPin className="h-5 w-5 text-gray-700" />
              <h2 className="text-lg font-semibold text-gray-900">
                {t('detail.shippingAddress')}
              </h2>
            </div>
            {shippingAddress ? (
              <div className="text-gray-700 space-y-1">
                <p>{shippingAddress.address_line1}</p>
                {shippingAddress.address_line2 && (
                  <p>{shippingAddress.address_line2}</p>
                )}
                {shippingLocation && <p>{shippingLocation}</p>}
              </div>
            ) : (
              <p className="text-gray-500">{t('detail.noShippingAddress')}</p>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Order Summary */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              {t('detail.summary')}
            </h2>
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">{t('detail.subtotal')}</span>
                <span className="text-gray-900 font-medium">
                  {price(order.total_amount)}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">{t('detail.shipping')}</span>
                <span className="text-gray-900 font-medium">
                  {order.shipping_method || t('detail.standardShipping')}
                </span>
              </div>
              <div className="pt-3 border-t border-gray-200">
                <div className="flex justify-between">
                  <span className="text-base font-semibold text-gray-900">
                    {t('detail.total')}
                  </span>
                  <span className="text-lg font-bold text-primary">
                    {price(order.total_amount)}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Payment Status */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <div className="flex items-center gap-2 mb-4">
              <CreditCard className="h-5 w-5 text-gray-700" />
              <h2 className="text-lg font-semibold text-gray-900">
                {t('detail.payment')}
              </h2>
            </div>
            <div className="flex items-center gap-2">
              {order.payment_status === 'SUCCESSFUL' && (
                <CheckCircle className="h-5 w-5 text-green-600" />
              )}
              <span
                className={`font-medium ${
                  PAYMENT_STATUS_COLORS[order.payment_status] ||
                  'text-yellow-600'
                }`}
              >
                {order.payment_status_label || order.payment_status}
              </span>
            </div>
          </div>

          {/* Order Status Timeline */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              {t('detail.statusTitle')}
            </h2>
            <div className="space-y-4">
              {TIMELINE_STATUSES.map((status, index) => {
                const isCompleted =
                  TIMELINE_STATUSES.indexOf(order.order_status) >= index
                const isCurrent = order.order_status === status

                return (
                  <div key={status} className="flex items-start gap-3">
                    <div
                      className={`mt-1 h-6 w-6 rounded-full flex items-center justify-center flex-shrink-0 ${
                        isCompleted
                          ? 'bg-primary text-white'
                          : 'bg-gray-200 text-gray-500'
                      }`}
                    >
                      {isCompleted && <CheckCircle className="h-4 w-4" />}
                    </div>
                    <div className="flex-1">
                      <p
                        className={`text-sm font-medium ${
                          isCurrent
                            ? 'text-primary'
                            : isCompleted
                              ? 'text-gray-900'
                              : 'text-gray-500'
                        }`}
                      >
                        {t(`detail.status.${status}`)}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
