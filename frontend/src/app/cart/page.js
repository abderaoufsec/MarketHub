'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { cartAPI } from '../../lib/api'
import { cartSubtotal, lineTotal } from '../../lib/cart'
import { usePrice } from '../../lib/currency'
import { useAuth } from '../../context/AuthContext'
import { Trash2, Plus, Minus, ShoppingBag } from 'lucide-react'
import Link from 'next/link'

export default function CartPage() {
  const router = useRouter()
  const t = useTranslations('cart')
  // Locale-aware DZD formatter (Phase 11) — dinars, never a `$`.
  const price = usePrice()
  const { isAuthenticated, isSeller } = useAuth()
  const [cart, setCart] = useState(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login')
      return
    }
    if (isSeller) {
      router.push('/seller/dashboard')
      return
    }
    fetchCart()
  }, [isAuthenticated, isSeller])

  const fetchCart = async () => {
    try {
      const response = await cartAPI.get()
      setCart(response.data)
    } catch (error) {
      console.error('Error fetching cart:', error)
    } finally {
      setLoading(false)
    }
  }

  const updateQuantity = async (itemId, newQuantity) => {
    if (newQuantity < 1) return
    setUpdating(true)

    try {
      await cartAPI.update(itemId, { quantity: newQuantity })
      await fetchCart()
    } catch (error) {
      console.error('Error updating quantity:', error)
    } finally {
      setUpdating(false)
    }
  }

  const removeItem = async (itemId) => {
    setUpdating(true)
    try {
      await cartAPI.remove(itemId)
      await fetchCart()
    } catch (error) {
      console.error('Error removing item:', error)
    } finally {
      setUpdating(false)
    }
  }

  const getTotal = () => cartSubtotal(cart?.items)

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="animate-pulse">
          <div className="bg-gray-300 h-8 rounded w-1/4 mb-8"></div>
          <div className="space-y-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="bg-gray-300 h-24 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  const items = cart?.items || []

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-gray-900 mb-8">{t('title')}</h1>

      {items.length === 0 ? (
        <div className="text-center py-12">
          <ShoppingBag className="h-24 w-24 text-gray-300 mx-auto mb-4" />
          <h2 className="text-2xl font-semibold text-gray-900 mb-2">
            {t('empty.title')}
          </h2>
          <p className="text-gray-600 mb-8">{t('empty.text')}</p>
          <Link href="/products" className="btn-primary inline-block">
            {t('empty.browseProducts')}
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Cart Items */}
          <div className="lg:col-span-2 space-y-4">
            {items.map((item) => (
              <div
                key={item.id}
                className="bg-white rounded-lg shadow-sm p-4 flex flex-col sm:flex-row items-start sm:items-center gap-4"
              >
                <img
                  src={
                    item.product?.images?.[0]?.image_url ||
                    '/placeholder-product.jpg'
                  }
                  alt={item.product?.name}
                  className="w-24 h-24 object-cover rounded-lg"
                  onError={(e) => {
                    e.target.src = '/placeholder-product.jpg'
                  }}
                />
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-gray-900">
                    {item.product?.name}
                  </h3>
                  <p className="text-sm text-gray-600">
                    {t('item.unitPrice', {
                      price: price(item.price_at_time_of_addition),
                    })}
                  </p>
                  {item.selected_attributes &&
                    Object.keys(item.selected_attributes).length > 0 && (
                      <p className="text-sm text-gray-500 mt-1">
                        {Object.entries(item.selected_attributes).map(
                          ([key, value]) => (
                            <span key={key} className="me-2">
                              {key}: {value}
                            </span>
                          )
                        )}
                      </p>
                    )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => updateQuantity(item.id, item.quantity - 1)}
                    disabled={updating}
                    aria-label={t('item.decreaseQuantity')}
                    className="p-1 rounded hover:bg-gray-100 disabled:opacity-50"
                  >
                    <Minus className="h-4 w-4" />
                  </button>
                  <span className="w-12 text-center font-semibold">
                    {item.quantity}
                  </span>
                  <button
                    onClick={() => updateQuantity(item.id, item.quantity + 1)}
                    disabled={updating}
                    aria-label={t('item.increaseQuantity')}
                    className="p-1 rounded hover:bg-gray-100 disabled:opacity-50"
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                </div>
                <div className="text-end sm:text-start sm:min-w-[100px]">
                  <p className="text-lg font-bold text-gray-900">
                    {price(lineTotal(item))}
                  </p>
                  <button
                    onClick={() => removeItem(item.id)}
                    disabled={updating}
                    aria-label={t('item.remove')}
                    className="text-red-600 hover:text-red-800 mt-2 flex items-center gap-1 text-sm disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                    {t('item.remove')}
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Order Summary */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-lg shadow-sm p-6 sticky top-4">
              <h2 className="text-xl font-bold text-gray-900 mb-4">
                {t('summary.title')}
              </h2>
              <div className="space-y-2 mb-4">
                <div className="flex justify-between">
                  <span className="text-gray-600">{t('summary.subtotal')}</span>
                  <span className="font-semibold">{price(getTotal())}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">{t('summary.shipping')}</span>
                  <span className="font-semibold text-green-600">
                    {t('summary.free')}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">
                    {t('summary.estimatedTax')}
                  </span>
                  <span className="font-semibold">{price(0)}</span>
                </div>
              </div>
              <div className="border-t pt-4 mb-4">
                <div className="flex justify-between text-lg font-bold">
                  <span>{t('summary.total')}</span>
                  <span className="text-primary">{price(getTotal())}</span>
                </div>
              </div>
              <Link
                href="/checkout"
                className="btn-primary w-full block text-center"
              >
                {t('summary.checkout')}
              </Link>
              <Link
                href="/products"
                className="btn-secondary w-full block text-center mt-3"
              >
                {t('summary.continueShopping')}
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
