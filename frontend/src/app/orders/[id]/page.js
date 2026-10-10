'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useAuth } from '../../../context/AuthContext'
import { ordersAPI } from '../../../lib/api'
import Link from 'next/link'
import {
  Package,
  Calendar,
  MapPin,
  CreditCard,
  Store,
  ArrowLeft,
  CheckCircle,
} from 'lucide-react'

const ORDER_STATUS = {
  PENDING: {
    label: 'Pending',
    color: 'bg-yellow-100 text-yellow-800',
    icon: '⏳',
  },
  PROCESSING: {
    label: 'Processing',
    color: 'bg-blue-100 text-blue-800',
    icon: '⚙️',
  },
  SHIPPED: {
    label: 'Shipped',
    color: 'bg-purple-100 text-purple-800',
    icon: '🚚',
  },
  DELIVERED: {
    label: 'Delivered',
    color: 'bg-green-100 text-green-800',
    icon: '✅',
  },
  CANCELLED: {
    label: 'Cancelled',
    color: 'bg-red-100 text-red-800',
    icon: '❌',
  },
}

const PAYMENT_STATUS = {
  PENDING: { label: 'Pending', color: 'text-yellow-600' },
  SUCCESSFUL: { label: 'Successful', color: 'text-green-600' },
  FAILED: { label: 'Failed', color: 'text-red-600' },
}

export default function OrderDetailPage() {
  const params = useParams()
  const router = useRouter()
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
        <p className="text-gray-500 text-lg">Order not found</p>
        <Link
          href="/orders"
          className="text-primary hover:text-secondary mt-4 inline-block"
        >
          Back to Orders
        </Link>
      </div>
    )
  }

  const statusInfo = ORDER_STATUS[order.order_status] || ORDER_STATUS.PENDING
  const paymentInfo =
    PAYMENT_STATUS[order.payment_status] || PAYMENT_STATUS.PENDING

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Back Button */}
      <Link
        href="/orders"
        className="inline-flex items-center text-gray-600 hover:text-primary mb-6"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Orders
      </Link>

      {/* Order Header */}
      <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Order #{order.id}
            </h1>
            <div className="flex items-center gap-2 text-sm text-gray-600 mt-2">
              <Calendar className="h-4 w-4" />
              <span>
                Placed on{' '}
                {new Date(order.order_date).toLocaleDateString('en-US', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </span>
            </div>
          </div>
          <span
            className={`px-4 py-2 rounded-full text-sm font-medium ${statusInfo.color}`}
          >
            {statusInfo.icon} {statusInfo.label}
          </span>
        </div>

        {/* Store Info */}
        {order.store_name && (
          <div className="pt-4 border-t border-gray-200">
            {order.store ? (
              <Link
                href={`/stores/${order.store.store_slug || order.store.store_slug}`}
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
              Order Items
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
                        {item.product?.name || 'Product'}
                      </Link>
                      {item.selected_attributes &&
                        Object.keys(item.selected_attributes).length > 0 && (
                          <div className="text-sm text-gray-600 mt-1">
                            {Object.entries(item.selected_attributes).map(
                              ([key, value]) => (
                                <span key={key} className="mr-3">
                                  {key}: {value}
                                </span>
                              )
                            )}
                          </div>
                        )}
                      <div className="text-sm text-gray-600 mt-1">
                        Quantity: {item.quantity}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold text-gray-900">
                        ${parseFloat(item.unit_price_at_purchase).toFixed(2)}
                      </div>
                      <div className="text-sm text-gray-600">each</div>
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
                Shipping Address
              </h2>
            </div>
            {order.shipping_address ? (
              <div className="text-gray-700 space-y-1">
                <p>{order.shipping_address.address_line1}</p>
                {order.shipping_address.address_line2 && (
                  <p>{order.shipping_address.address_line2}</p>
                )}
                <p>
                  {order.shipping_address.city},{' '}
                  {order.shipping_address.state_province}{' '}
                  {order.shipping_address.postal_code}
                </p>
                <p>{order.shipping_address.country}</p>
              </div>
            ) : (
              <p className="text-gray-500">No shipping address provided</p>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Order Summary */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Order Summary
            </h2>
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Subtotal</span>
                <span className="text-gray-900 font-medium">
                  ${parseFloat(order.total_amount).toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Shipping</span>
                <span className="text-gray-900 font-medium">
                  {order.shipping_method || 'Standard'}
                </span>
              </div>
              <div className="pt-3 border-t border-gray-200">
                <div className="flex justify-between">
                  <span className="text-base font-semibold text-gray-900">
                    Total
                  </span>
                  <span className="text-lg font-bold text-primary">
                    ${parseFloat(order.total_amount).toFixed(2)}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Payment Status */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <div className="flex items-center gap-2 mb-4">
              <CreditCard className="h-5 w-5 text-gray-700" />
              <h2 className="text-lg font-semibold text-gray-900">Payment</h2>
            </div>
            <div className="flex items-center gap-2">
              {order.payment_status === 'SUCCESSFUL' && (
                <CheckCircle className="h-5 w-5 text-green-600" />
              )}
              <span className={`font-medium ${paymentInfo.color}`}>
                {paymentInfo.label}
              </span>
            </div>
          </div>

          {/* Order Status Timeline */}
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Order Status
            </h2>
            <div className="space-y-4">
              {['PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED'].map(
                (status, index) => {
                  const isCompleted =
                    ['PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED'].indexOf(
                      order.order_status
                    ) >= index
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
                          {ORDER_STATUS[status].label}
                        </p>
                      </div>
                    </div>
                  )
                }
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
