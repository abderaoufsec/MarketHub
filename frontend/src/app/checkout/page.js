'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { cartAPI, ordersAPI, addressesAPI } from '../../lib/api'
import { apiErrorMessage, parseApiError } from '../../lib/errors'
import { cartSubtotal, lineTotal } from '../../lib/cart'
import { usePrice } from '../../lib/currency'
import { useAuth } from '../../context/AuthContext'
import LocationPicker from '../../components/common/LocationPicker'
import {
  CreditCard,
  MapPin,
  Package,
  AlertCircle,
  CheckCircle,
  Plus,
  Loader2,
} from 'lucide-react'
import toast from 'react-hot-toast'

// One key per checkout attempt: retrying after a network timeout returns the
// order that was already created instead of charging the buyer twice.
const newIdempotencyKey = () =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`

export default function CheckoutPage() {
  const router = useRouter()
  const t = useTranslations('checkout')
  // Locale-aware DZD formatter (Phase 11) — replaces the old `$` hard-coding.
  const formatPrice = usePrice()
  const { isAuthenticated } = useAuth()
  const [cart, setCart] = useState(null)
  const [addresses, setAddresses] = useState([])
  const [loading, setLoading] = useState(true)
  const [processing, setProcessing] = useState(false)
  const [error, setError] = useState('')
  const [priceChanges, setPriceChanges] = useState([])
  const [selectedAddressId, setSelectedAddressId] = useState(null)
  const [showNewAddressForm, setShowNewAddressForm] = useState(false)
  const [paymentMethod, setPaymentMethod] = useState('credit_card')
  const [idempotencyKey] = useState(newIdempotencyKey)
  const [shippingInfo, setShippingInfo] = useState({
    address_line1: '',
    address_line2: '',
    // Phase 11: the free-text city/state/postal trio is gone — an address is
    // a street line plus a wilaya and an optional commune.
    wilaya_id: null,
    commune_id: null,
    is_default: false,
  })

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login')
      return
    }
    fetchCart()
    fetchAddresses()
  }, [isAuthenticated])

  const fetchCart = async () => {
    try {
      const response = await cartAPI.get()
      setCart(response.data)
      if (!response.data?.items || response.data.items.length === 0) {
        router.push('/cart')
      }
    } catch (error) {
      console.error('Error fetching cart:', error)
      setError(t('errors.loadCart'))
    } finally {
      setLoading(false)
    }
  }

  const fetchAddresses = async () => {
    try {
      const response = await addressesAPI.list()
      const addressesData = response.data.results || response.data || []
      setAddresses(addressesData)
      // Select default address if available
      const defaultAddress = addressesData.find((addr) => addr.is_default)
      if (defaultAddress) {
        setSelectedAddressId(defaultAddress.id)
      } else if (addressesData.length > 0) {
        setSelectedAddressId(addressesData[0].id)
      }
    } catch (error) {
      console.error('Error fetching addresses:', error)
    }
  }

  const handleCreateAddress = async (e) => {
    e.preventDefault()
    setError('')

    try {
      const response = await addressesAPI.create(shippingInfo)
      toast.success(t('addressSaved'))
      await fetchAddresses()
      setSelectedAddressId(response.data.id)
      setShowNewAddressForm(false)
      setShippingInfo({
        address_line1: '',
        address_line2: '',
        wilaya_id: null,
        commune_id: null,
        is_default: false,
      })
    } catch (error) {
      console.error('Error creating address:', error)
      const errorMsg = apiErrorMessage(error, t('errors.saveAddress'))
      setError(errorMsg)
      toast.error(errorMsg)
    }
  }

  // Checkout refused to charge a stale price: accept the catalogue prices and
  // ask the buyer to confirm the new total.
  const applyPriceChanges = async (changes) => {
    setPriceChanges(changes)
    try {
      const response = await cartAPI.refreshPrices()
      setCart(response.data.cart)
    } catch (refreshError) {
      console.error('Error refreshing cart prices:', refreshError)
    }
    const message =
      changes.length === 1
        ? t('priceChanges.toastOne', {
            name: changes[0].product_name,
            price: formatPrice(changes[0].new_price),
          })
        : t('priceChanges.toastMany')
    toast.error(message, { duration: 6000 })
  }

  const handleCheckout = async (e) => {
    e.preventDefault()
    setError('')
    setProcessing(true)

    try {
      // Validate cart has items
      if (!cart?.items || cart.items.length === 0) {
        setError(t('errors.emptyCart'))
        return
      }

      // If using new address form, create address first
      let addressId = selectedAddressId

      if (showNewAddressForm && !addressId) {
        // Validate required fields — street line + wilaya (commune optional).
        if (!shippingInfo.address_line1 || !shippingInfo.wilaya_id) {
          setError(t('errors.requiredAddressFields'))
          return
        }

        const addressResponse = await addressesAPI.create(shippingInfo)
        addressId = addressResponse.data.id
      }

      if (!addressId) {
        setError(t('errors.selectAddress'))
        return
      }

      // One call, one transaction: the backend creates the order(s), reserves
      // stock and captures the payment together. Payment happens here — there
      // is no second "pay again" request after the order is created.
      const response = await ordersAPI.checkout({
        shipping_address_id: addressId,
        shipping_method: 'standard',
        idempotency_key: idempotencyKey,
      })

      const orderId = response.data.orders?.[0]?.id

      toast.success(t('orderPlaced'))
      router.push(`/orders/${orderId}?success=true`)
    } catch (checkoutError) {
      console.error('Checkout error:', checkoutError)

      // One read of the Phase 9 envelope: branch on `code`, then let the
      // `details` payload drive the price-delta recovery.
      const failure = parseApiError(checkoutError)

      if (failure.code === 'price_changed') {
        await applyPriceChanges(failure.details || [])
        return
      }

      const errorMsg = apiErrorMessage(checkoutError, t('errors.processOrder'))
      setError(errorMsg)
      toast.error(errorMsg)
    } finally {
      setProcessing(false)
    }
  }

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target
    setShippingInfo({
      ...shippingInfo,
      [name]: type === 'checkbox' ? checked : value,
    })
  }

  const getTotal = () => cartSubtotal(cart?.items)

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="animate-pulse">
          <div className="bg-gray-300 h-8 rounded w-1/4 mb-8"></div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-2 bg-gray-300 h-96 rounded"></div>
            <div className="bg-gray-300 h-64 rounded"></div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-gray-900 mb-8">{t('title')}</h1>

      {priceChanges.length > 0 && (
        <div className="mb-6 bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-lg">
          <p className="font-semibold flex items-center">
            <AlertCircle className="h-5 w-5 me-2" />
            {t('priceChanges.title')}
          </p>
          <p className="text-sm mt-1">{t('priceChanges.description')}</p>
          <ul className="mt-2 space-y-1 text-sm">
            {priceChanges.map((change) => (
              <li key={change.product_id}>
                {t('priceChanges.line', {
                  name: change.product_name,
                  oldPrice: formatPrice(change.old_price),
                  newPrice: formatPrice(change.new_price),
                })}
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center">
          <AlertCircle className="h-5 w-5 me-2" />
          <span>{error}</span>
        </div>
      )}

      <form
        onSubmit={showNewAddressForm ? handleCreateAddress : handleCheckout}
      >
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Checkout Form */}
          <div className="lg:col-span-2 space-y-6">
            {/* Shipping Information */}
            <div className="bg-white rounded-lg shadow-sm p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold text-gray-900 flex items-center">
                  <MapPin className="h-5 w-5 me-2" />
                  {t('shippingAddress')}
                </h2>
                {!showNewAddressForm && (
                  <button
                    type="button"
                    onClick={() => setShowNewAddressForm(true)}
                    className="flex items-center gap-2 text-sm text-primary hover:text-secondary"
                  >
                    <Plus className="h-4 w-4" />
                    {t('addNewAddress')}
                  </button>
                )}
              </div>

              {!showNewAddressForm ? (
                // Address Selection
                <div className="space-y-3">
                  {addresses.length > 0 ? (
                    addresses.map((address) => (
                      <label
                        key={address.id}
                        className={`block p-4 border-2 rounded-lg cursor-pointer transition-all ${
                          selectedAddressId === address.id
                            ? 'border-primary bg-primary/5'
                            : 'border-gray-200 hover:border-gray-300'
                        }`}
                      >
                        <input
                          type="radio"
                          name="address"
                          value={address.id}
                          checked={selectedAddressId === address.id}
                          onChange={(e) =>
                            setSelectedAddressId(parseInt(e.target.value))
                          }
                          className="sr-only"
                        />
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              <span className="font-semibold text-gray-900">
                                {address.address_line1}
                              </span>
                              {address.is_default && (
                                <span className="px-2 py-0.5 text-xs bg-primary text-white rounded">
                                  {t('defaultBadge')}
                                </span>
                              )}
                            </div>
                            {address.address_line2 && (
                              <p className="text-sm text-gray-600">
                                {address.address_line2}
                              </p>
                            )}
                            <p className="text-sm text-gray-600">
                              {[address.commune?.name, address.wilaya?.name]
                                .filter(Boolean)
                                .join(', ')}
                            </p>
                          </div>
                          {selectedAddressId === address.id && (
                            <CheckCircle className="h-5 w-5 text-primary flex-shrink-0" />
                          )}
                        </div>
                      </label>
                    ))
                  ) : (
                    <div className="text-center py-8 text-gray-500">
                      <p>{t('noAddresses')}</p>
                    </div>
                  )}
                </div>
              ) : (
                // New Address Form
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      {t('addressForm.addressLine1')}
                      <span className="text-red-500"> *</span>
                    </label>
                    <input
                      type="text"
                      name="address_line1"
                      required
                      value={shippingInfo.address_line1}
                      onChange={handleInputChange}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                      placeholder={t('addressForm.streetPlaceholder')}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      {t('addressForm.addressLine2')}
                    </label>
                    <input
                      type="text"
                      name="address_line2"
                      value={shippingInfo.address_line2}
                      onChange={handleInputChange}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                      placeholder={t('addressForm.addressLine2Placeholder')}
                    />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Phase 11: wilaya → commune picker instead of free-text
                        city/province/postal/country. */}
                    <div className="md:col-span-2">
                      <LocationPicker
                        wilayaId={shippingInfo.wilaya_id}
                        communeId={shippingInfo.commune_id}
                        onChange={({ wilayaId, communeId }) =>
                          setShippingInfo((prev) => ({
                            ...prev,
                            wilaya_id: wilayaId,
                            commune_id: communeId,
                          }))
                        }
                        required
                      />
                    </div>
                  </div>
                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      name="is_default"
                      id="is_default"
                      checked={shippingInfo.is_default}
                      onChange={handleInputChange}
                      className="h-4 w-4 text-primary focus:ring-primary border-gray-300 rounded"
                    />
                    <label
                      htmlFor="is_default"
                      className="ms-2 text-sm text-gray-700"
                    >
                      {t('addressForm.setAsDefault')}
                    </label>
                  </div>
                  <div className="flex gap-3">
                    <button type="submit" className="btn-primary flex-1">
                      {t('addressForm.save')}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowNewAddressForm(false)
                        setShippingInfo({
                          address_line1: '',
                          address_line2: '',
                          wilaya_id: null,
                          commune_id: null,
                          is_default: false,
                        })
                      }}
                      className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                    >
                      {t('addressForm.cancel')}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Payment Information */}
            {!showNewAddressForm && (
              <div className="bg-white rounded-lg shadow-sm p-6">
                <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center">
                  <CreditCard className="h-5 w-5 me-2" />
                  {t('payment.title')}
                </h2>

                <div className="space-y-3 mb-4">
                  <label className="flex items-center p-4 border-2 rounded-lg cursor-pointer border-primary bg-primary/5">
                    <input
                      type="radio"
                      name="payment_method"
                      value="credit_card"
                      checked={paymentMethod === 'credit_card'}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                      className="h-4 w-4 text-primary"
                    />
                    <CreditCard className="h-5 w-5 mx-3 text-primary" />
                    <span className="font-medium">
                      {t('payment.creditCard')}
                    </span>
                  </label>
                </div>

                <div className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded-lg">
                  <p className="text-sm">
                    <strong>{t('payment.simulatedTitle')}</strong>{' '}
                    {t('payment.simulatedBody')}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Order Summary */}
          {!showNewAddressForm && (
            <div className="lg:col-span-1">
              <div className="bg-white rounded-lg shadow-sm p-6 sticky top-4">
                <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center">
                  <Package className="h-5 w-5 me-2" />
                  {t('summary.title')}
                </h2>

                <div className="space-y-3 mb-4 max-h-64 overflow-y-auto">
                  {cart?.items?.map((item) => (
                    <div key={item.id} className="flex items-center gap-3">
                      <img
                        src={
                          item.product?.images?.[0]?.image_url ||
                          '/placeholder-product.jpg'
                        }
                        alt={item.product?.name}
                        className="w-16 h-16 object-cover rounded"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-gray-900 truncate">
                          {item.product?.name}
                        </p>
                        <p className="text-sm text-gray-600">
                          {t('summary.lineQuantity', {
                            qty: item.quantity,
                            price: formatPrice(item.price_at_time_of_addition),
                          })}
                        </p>
                      </div>
                      <p className="text-sm font-semibold">
                        {formatPrice(lineTotal(item))}
                      </p>
                    </div>
                  ))}
                </div>

                <div className="border-t pt-4 space-y-2 mb-4">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">
                      {t('summary.subtotal')}
                    </span>
                    <span className="font-semibold">
                      {formatPrice(getTotal())}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">
                      {t('summary.shipping')}
                    </span>
                    <span className="font-semibold">{t('summary.free')}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">{t('summary.tax')}</span>
                    <span className="font-semibold">{formatPrice(0)}</span>
                  </div>
                </div>

                <div className="border-t pt-4 mb-6">
                  <div className="flex justify-between text-lg font-bold">
                    <span>{t('summary.total')}</span>
                    <span className="text-primary">
                      {formatPrice(getTotal())}
                    </span>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={processing || !selectedAddressId}
                  className="w-full btn-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {processing ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {t('summary.processing')}
                    </>
                  ) : (
                    t('summary.placeOrder')
                  )}
                </button>

                <p className="text-xs text-gray-500 text-center mt-4">
                  {t('summary.termsNote')}
                </p>
              </div>
            </div>
          )}
        </div>
      </form>
    </div>
  )
}
