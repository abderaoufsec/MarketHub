'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { productsAPI, cartAPI, reviewsAPI, wishlistAPI } from '../../lib/api'
import { apiErrorMessage } from '../../lib/errors'
import { useAuth } from '../../context/AuthContext'
import {
  ShoppingCart,
  Store,
  Package,
  AlertCircle,
  CheckCircle,
  Heart,
  Star,
  MessageSquare,
  Phone,
  MessageCircle,
  MapPin,
  User,
} from 'lucide-react'
import Link from 'next/link'
import ReviewModal from './ReviewModal'
import ProductCard from './ProductCard'
import SafeImage from '../common/SafeImage'
import toast from 'react-hot-toast'
import { useLocale, useTranslations } from 'next-intl'
import { intlLocale } from '../../i18n/config'
import { usePrice } from '../../lib/currency'

/**
 * One listing's public page (Phase 13).
 *
 * Extracted from the old `/products/[id]` route so both entry points render
 * the same view: the canonical `/l/<slug>-<id>` and the legacy
 * `/products/<id>`. Whichever one you arrive on, once the row is loaded the
 * page normalizes the address bar to `canonical_path` — a renamed ad keeps
 * its old links working instead of stranding them on a stale slug.
 *
 * `listing_type` branches the *page*, mirroring the API: a store SKU keeps
 * cart, stock and the store link; everything else is an individual's
 * classified — no inventory, a contact block instead of a checkout, and
 * "similar / more from this seller" rails instead of a store page.
 */
export default function ProductDetail({ productId }) {
  const t = useTranslations('products')
  const locale = useLocale()
  const price = usePrice()
  const router = useRouter()
  const { isAuthenticated, isSeller } = useAuth()
  const [product, setProduct] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedImage, setSelectedImage] = useState(0)
  const [brokenImages, setBrokenImages] = useState({})
  const [quantity, setQuantity] = useState(1)
  const [selectedAttributes, setSelectedAttributes] = useState({})
  const [addingToCart, setAddingToCart] = useState(false)
  const [cartMessage, setCartMessage] = useState(null)
  const [isWishlisted, setIsWishlisted] = useState(false)
  const [wishlistLoading, setWishlistLoading] = useState(false)
  const [showReviewModal, setShowReviewModal] = useState(false)
  const [userReview, setUserReview] = useState(null)
  const [similar, setSimilar] = useState([])
  const [alsoFromSeller, setAlsoFromSeller] = useState([])

  useEffect(() => {
    if (productId) {
      fetchProduct()
      if (isAuthenticated) {
        checkWishlistStatus()
        checkUserReview()
      }
    }
  }, [productId, isAuthenticated])

  // Phase 13: only a live STORE_PRODUCT is buyable — the same rule the API
  // enforces (cart add would answer 400 otherwise).
  const buyable =
    product &&
    product.listing_type === 'STORE_PRODUCT' &&
    product.store &&
    product.is_available

  useEffect(() => {
    if (!product) return
    let cancelled = false
    productsAPI
      .similar(product.id)
      .then((response) => {
        if (!cancelled) {
          setSimilar(
            (response.data || []).filter((row) => row.id !== product.id)
          )
        }
      })
      .catch(() => {})
    if (!product.store) {
      productsAPI
        .moreFromSeller(product.id)
        .then((response) => {
          if (!cancelled) {
            setAlsoFromSeller(
              (response.data || []).filter((row) => row.id !== product.id)
            )
          }
        })
        .catch(() => {})
    }
    return () => {
      cancelled = true
    }
  }, [product?.id, product?.store])

  const fetchProduct = async () => {
    try {
      setLoading(true)
      const response = await productsAPI.get(productId)
      const row = response.data
      setProduct(row)
      // One canonical URL per listing: /l/<slug>-<id>. A stale slug (the ad
      // was renamed) and the legacy /products/<id> both land here and get
      // the canonical path back — same page, canonical address.
      if (
        row?.canonical_path &&
        typeof window !== 'undefined' &&
        window.location.pathname !== row.canonical_path
      ) {
        router.replace(row.canonical_path)
      }
    } catch (error) {
      console.error('Error fetching product:', error)
    } finally {
      setLoading(false)
    }
  }

  const checkWishlistStatus = async () => {
    try {
      const response = await wishlistAPI.check(productId)
      setIsWishlisted(response.data.is_wishlisted)
    } catch (error) {
      console.error('Error checking wishlist:', error)
    }
  }

  const checkUserReview = async () => {
    try {
      const response = await reviewsAPI.checkUserReview(productId)
      if (response.data.has_reviewed) {
        setUserReview(response.data.review)
      }
    } catch (error) {
      console.error('Error checking review:', error)
    }
  }

  const toggleWishlist = async () => {
    if (!isAuthenticated) {
      router.push('/login')
      return
    }

    setWishlistLoading(true)
    try {
      if (isWishlisted) {
        await wishlistAPI.remove(productId)
        setIsWishlisted(false)
        toast.success(t('removedFromWishlist'))
      } else {
        await wishlistAPI.add(productId)
        setIsWishlisted(true)
        toast.success(t('addedToWishlist'))
      }
    } catch (error) {
      console.error('Error toggling wishlist:', error)
      toast.error(t('wishlistError'))
    } finally {
      setWishlistLoading(false)
    }
  }

  const handleAddToCart = async () => {
    if (!isAuthenticated) {
      router.push('/login')
      return
    }

    if (isSeller) {
      setCartMessage({
        type: 'error',
        text: t('sellerCannotCart'),
      })
      setTimeout(() => setCartMessage(null), 3000)
      return
    }

    try {
      setAddingToCart(true)
      await cartAPI.add({
        product_id: product.id,
        quantity,
        selected_attributes: selectedAttributes,
      })
      setCartMessage({ type: 'success', text: t('addedToCart') })
      setTimeout(() => setCartMessage(null), 3000)
    } catch (error) {
      setCartMessage({
        type: 'error',
        text: apiErrorMessage(error, t('addToCartError')),
      })
      setTimeout(() => setCartMessage(null), 3000)
    } finally {
      setAddingToCart(false)
    }
  }

  const handleReviewSubmitted = () => {
    fetchProduct()
    checkUserReview()
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="animate-pulse">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="bg-gray-300 h-96 rounded-lg"></div>
            <div>
              <div className="bg-gray-300 h-8 rounded w-3/4 mb-4"></div>
              <div className="bg-gray-300 h-4 rounded w-1/2 mb-8"></div>
              <div className="bg-gray-300 h-24 rounded mb-4"></div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (!product) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8 text-center">
        <p className="text-gray-500 text-lg">{t('notFound')}</p>
        <Link
          href="/products"
          className="text-primary hover:text-secondary mt-4 inline-block"
        >
          {t('backToProducts')}
        </Link>
      </div>
    )
  }

  const images = product.images || []
  const selected = images[selectedImage]
  // Uploaded photos resolve to the card/detail variants; legacy rows still
  // carry only an external URL. A failed load falls back to the placeholder.
  const frameUrl = selected?.full_url || selected?.url || selected?.image_url
  const mainImage = brokenImages[selectedImage]
    ? '/placeholder-product.jpg'
    : frameUrl || '/placeholder-product.jpg'
  const markBroken = (index) =>
    setBrokenImages((current) => ({ ...current, [index]: true }))
  const priceMode = product.price_mode || 'FIXED'
  const hasPrice =
    product.base_price !== null && product.base_price !== undefined
  const isClassified = product.listing_type !== 'STORE_PRODUCT'

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Breadcrumb */}
      <nav className="mb-4 text-sm">
        <Link href="/" className="text-gray-500 hover:text-primary">
          {t('breadcrumb.home')}
        </Link>
        <span className="mx-2 text-gray-400">/</span>
        <Link href="/products" className="text-gray-500 hover:text-primary">
          {t('breadcrumb.products')}
        </Link>
        <span className="mx-2 text-gray-400">/</span>
        <span className="text-gray-900">{product.name}</span>
      </nav>

      {cartMessage && (
        <div
          className={`mb-4 p-4 rounded-lg flex items-center ${
            cartMessage.type === 'success'
              ? 'bg-green-50 border border-green-200 text-green-700'
              : 'bg-red-50 border border-red-200 text-red-700'
          }`}
        >
          {cartMessage.type === 'success' ? (
            <CheckCircle className="h-5 w-5 me-2 flex-shrink-0" />
          ) : (
            <AlertCircle className="h-5 w-5 me-2 flex-shrink-0" />
          )}
          <span>{cartMessage.text}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Images */}
        <div>
          <div className="relative bg-gray-100 rounded-lg overflow-hidden mb-4 aspect-square">
            <SafeImage
              src={mainImage}
              alt={product.name}
              fill
              sizes="(max-width: 768px) 100vw, 50vw"
              priority
              blurDataURL={selected?.lqip}
              className="object-cover"
              onError={() => markBroken(selectedImage)}
            />
          </div>
          {images.length > 1 && (
            <div className="grid grid-cols-4 gap-2">
              {images.map((img, index) => (
                <button
                  key={img.id || index}
                  onClick={() => setSelectedImage(index)}
                  className={`border-2 rounded-lg overflow-hidden transition-all ${
                    selectedImage === index
                      ? 'border-primary ring-2 ring-primary'
                      : 'border-gray-300'
                  }`}
                >
                  <SafeImage
                    src={
                      brokenImages[index]
                        ? '/placeholder-product.jpg'
                        : img.thumb_url || img.url || img.image_url
                    }
                    alt={`${product.name} ${index + 1}`}
                    width={160}
                    height={80}
                    className="w-full h-20 object-cover"
                    onError={() => markBroken(index)}
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Product Info */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <h1 className="text-3xl font-bold text-gray-900">{product.name}</h1>
            {product.listing_type_label && (
              <span className="text-xs bg-gray-100 text-gray-700 px-3 py-1 rounded-full flex-shrink-0">
                {product.listing_type_label}
              </span>
            )}
          </div>

          {product.store ? (
            <Link
              href={`/stores/${product.store?.store_slug}`}
              className="flex items-center text-gray-600 hover:text-primary mb-4 w-fit"
            >
              <Store className="h-4 w-4 me-1" />
              <span className="text-sm">{product.store?.store_name}</span>
            </Link>
          ) : (
            product.seller_name && (
              <p className="flex items-center text-gray-600 mb-4 text-sm">
                <User className="h-4 w-4 me-1" />
                <span>{product.seller_name}</span>
              </p>
            )
          )}

          {/* Rating & Reviews */}
          <div className="flex items-center gap-4 mb-4">
            <div className="flex items-center gap-1">
              {[...Array(5)].map((_, i) => (
                <Star
                  key={i}
                  className={`h-5 w-5 ${
                    i < Math.round(product.average_rating || 0)
                      ? 'fill-yellow-400 text-yellow-400'
                      : 'text-gray-300'
                  }`}
                />
              ))}
              <span className="ms-2 text-sm text-gray-600">
                {product.average_rating
                  ? product.average_rating.toFixed(1)
                  : '0.0'}{' '}
                ({t('reviewCount', { n: product.review_count || 0 })})
              </span>
            </div>
          </div>

          {/* Phase 12: `category` is the nested {id, slug, name} object. */}
          <div className="flex flex-wrap items-center gap-2 mb-4">
            {product.category && (
              <span className="inline-block text-xs bg-blue-100 text-primary px-3 py-1 rounded-full">
                {product.category.name || product.category}
              </span>
            )}
            {product.wilaya_name && (
              <span className="inline-block text-xs bg-gray-100 text-gray-700 px-3 py-1 rounded-full flex items-center">
                <MapPin className="h-3 w-3 me-1" />
                {product.wilaya_name}
              </span>
            )}
          </div>

          <div className="flex items-baseline gap-3 mb-6">
            <div className="text-4xl font-bold text-primary">
              {priceMode === 'ON_REQUEST' || !hasPrice
                ? t('priceOnRequest')
                : priceMode === 'FREE'
                  ? t('priceFree')
                  : priceMode === 'EXCHANGE'
                    ? t('priceExchange')
                    : price(product.base_price)}
            </div>
            {priceMode === 'NEGOTIABLE' && (
              <span className="text-sm bg-yellow-100 text-yellow-800 px-3 py-1 rounded-full">
                {t('negotiable')}
              </span>
            )}
          </div>

          <div className="mb-6 pb-6 border-b">
            <h2 className="text-lg font-semibold mb-2">{t('description')}</h2>
            <p className="text-gray-600 whitespace-pre-wrap">
              {product.description}
            </p>
          </div>

          {product.attributes && product.attributes.length > 0 && (
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-3">{t('options')}</h3>
              <div className="space-y-4">
                {product.attributes.map((attr) => (
                  <div key={attr.id}>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      {attr.attribute_name}
                    </label>
                    <select
                      value={selectedAttributes[attr.attribute_name] || ''}
                      onChange={(e) =>
                        setSelectedAttributes({
                          ...selectedAttributes,
                          [attr.attribute_name]: e.target.value,
                        })
                      }
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                    >
                      <option value="">
                        {t('selectAttribute', { name: attr.attribute_name })}
                      </option>
                      <option value={attr.attribute_value}>
                        {attr.attribute_value}
                      </option>
                    </select>
                  </div>
                ))}
              </div>
            </div>
          )}

          {isClassified ? (
            /* ---- Contact-first (Phase 13): no inventory, no checkout. ---- */
            <div className="mb-6 rounded-lg border border-gray-200 bg-gray-50 p-4">
              <h3 className="text-lg font-semibold mb-3">
                {t('contactSeller')}
              </h3>
              <div className="space-y-2 text-sm text-gray-700">
                {product.seller_name && (
                  <p className="flex items-center">
                    <User className="h-4 w-4 me-2 text-gray-500" />
                    {product.seller_name}
                  </p>
                )}
                {product.wilaya_name && (
                  <p className="flex items-center">
                    <MapPin className="h-4 w-4 me-2 text-gray-500" />
                    {product.wilaya_name}
                  </p>
                )}
                {product.seller_phone ? (
                  product.contact_mode === 'WHATSAPP' ? (
                    <a
                      href={`https://wa.me/${product.seller_phone.replace(
                        /[^\d]/g,
                        ''
                      )}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
                    >
                      <MessageCircle className="h-4 w-4" />
                      {t('whatsapp')}
                    </a>
                  ) : (
                    <a
                      href={`tel:${product.seller_phone}`}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-secondary"
                    >
                      <Phone className="h-4 w-4" />
                      {product.seller_phone}
                    </a>
                  )
                ) : (
                  <p className="text-gray-500">{t('contactThroughChat')}</p>
                )}
              </div>
            </div>
          ) : (
            <>
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('quantity')}
                </label>
                <input
                  type="number"
                  min="1"
                  max="10"
                  value={quantity}
                  onChange={(e) =>
                    setQuantity(Math.max(1, parseInt(e.target.value) || 1))
                  }
                  className="w-24 border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                />
              </div>

              <div className="flex items-center gap-2 mb-6 text-sm">
                <Package
                  className={`h-5 w-5 ${
                    product.is_available ? 'text-green-600' : 'text-red-600'
                  }`}
                />
                <span
                  className={
                    product.is_available ? 'text-green-600' : 'text-red-600'
                  }
                >
                  {product.is_available ? t('inStock') : t('outOfStock')}
                </span>
              </div>
            </>
          )}

          <div className="flex gap-3 mb-6">
            {buyable ? (
              <button
                onClick={handleAddToCart}
                disabled={addingToCart || isSeller}
                className="flex-1 btn-primary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ShoppingCart className="h-5 w-5" />
                {addingToCart ? t('adding') : t('addToCart')}
              </button>
            ) : (
              <span className="flex-1 text-center text-sm text-gray-500 self-center">
                {isClassified ? t('contactInsteadOfCart') : t('notForSale')}
              </span>
            )}
            <button
              onClick={toggleWishlist}
              disabled={wishlistLoading}
              className={`p-3 border-2 rounded-lg transition-colors ${
                isWishlisted
                  ? 'border-red-500 text-red-500 hover:bg-red-50'
                  : 'border-gray-300 hover:border-primary hover:text-primary'
              }`}
              title={
                isWishlisted ? t('removeFromWishlist') : t('addToWishlist')
              }
            >
              <Heart
                className={`h-6 w-6 ${isWishlisted ? 'fill-red-500' : ''}`}
              />
            </button>
          </div>

          {/* Write Review Button — purchases only, so store SKUs only. */}
          {!isClassified && isAuthenticated && !isSeller && (
            <button
              onClick={() => setShowReviewModal(true)}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 mb-4"
            >
              <MessageSquare className="h-5 w-5" />
              {userReview ? t('editYourReview') : t('writeReview')}
            </button>
          )}

          {isSeller && (
            <p className="text-sm text-gray-500 text-center">
              {t('sellersCannotPurchase')}
            </p>
          )}

          {/* Additional Info */}
          <div className="mt-8 pt-6 border-t">
            <h3 className="text-lg font-semibold mb-3">
              {t('productInformation')}
            </h3>
            <dl className="space-y-2 text-sm">
              {isClassified ? (
                <>
                  <div className="flex">
                    <dt className="text-gray-600 w-32">{t('adNumber')}</dt>
                    <dd className="text-gray-900 font-medium">#{product.id}</dd>
                  </div>
                  <div className="flex">
                    <dt className="text-gray-600 w-32">
                      {t('categoryInfoLabel')}
                    </dt>
                    <dd className="text-gray-900 font-medium">
                      {product.category?.name ||
                        product.category ||
                        t('general')}
                    </dd>
                  </div>
                  {product.expires_at && (
                    <div className="flex">
                      <dt className="text-gray-600 w-32">
                        {t('expiresOnLabel')}
                      </dt>
                      <dd className="text-gray-900 font-medium">
                        {new Intl.DateTimeFormat(intlLocale(locale), {
                          dateStyle: 'medium',
                        }).format(new Date(product.expires_at))}
                      </dd>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div className="flex">
                    <dt className="text-gray-600 w-32">{t('sku')}</dt>
                    <dd className="text-gray-900 font-medium">{product.id}</dd>
                  </div>
                  <div className="flex">
                    <dt className="text-gray-600 w-32">
                      {t('categoryInfoLabel')}
                    </dt>
                    <dd className="text-gray-900 font-medium">
                      {product.category?.name ||
                        product.category ||
                        t('general')}
                    </dd>
                  </div>
                  <div className="flex">
                    <dt className="text-gray-600 w-32">{t('availability')}</dt>
                    <dd
                      className={`font-medium ${
                        product.is_available ? 'text-green-600' : 'text-red-600'
                      }`}
                    >
                      {product.is_available ? t('inStock') : t('outOfStock')}
                    </dd>
                  </div>
                </>
              )}
            </dl>
          </div>
        </div>
      </div>

      {/* Reviews Section */}
      <div className="mt-16 border-t pt-8">
        <h2 className="text-2xl font-bold text-gray-900 mb-6">
          {t('customerReviews', { n: product.review_count || 0 })}
        </h2>

        {product.reviews && product.reviews.length > 0 ? (
          <div className="space-y-6">
            {product.reviews.map((review) => (
              <div key={review.id} className="border-b pb-6">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-gray-900">
                        {review.user_name}
                      </span>
                      <div className="flex items-center">
                        {[...Array(5)].map((_, i) => (
                          <Star
                            key={i}
                            className={`h-4 w-4 ${
                              i < review.rating
                                ? 'fill-yellow-400 text-yellow-400'
                                : 'text-gray-300'
                            }`}
                          />
                        ))}
                      </div>
                    </div>
                    <p className="text-xs text-gray-500">
                      {new Intl.DateTimeFormat(intlLocale(locale), {
                        dateStyle: 'medium',
                      }).format(new Date(review.created_at))}
                    </p>
                  </div>
                </div>
                <p className="text-gray-700 whitespace-pre-wrap">
                  {review.comment}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12 bg-gray-50 rounded-lg">
            <MessageSquare className="h-12 w-12 text-gray-400 mx-auto mb-3" />
            <p className="text-gray-600 mb-2">{t('noReviews')}</p>
            {!isClassified && (
              <p className="text-sm text-gray-500">{t('beFirst')}</p>
            )}
          </div>
        )}
      </div>

      {/* Store link (SKUs) or the seller's other live ads (classifieds). */}
      {product.store ? (
        <div className="mt-16">
          <h2 className="text-2xl font-bold text-gray-900 mb-6">
            {t('moreFromStore')}
          </h2>
          <Link
            href={`/stores/${product.store?.store_slug}`}
            className="text-primary hover:text-secondary"
          >
            {t('viewAllFrom', { store: product.store?.store_name })} →
          </Link>
        </div>
      ) : (
        alsoFromSeller.length > 0 && (
          <div className="mt-16">
            <h2 className="text-2xl font-bold text-gray-900 mb-6">
              {t('moreFromSeller')}
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {alsoFromSeller.slice(0, 4).map((row, index) => (
                <ProductCard key={row.id} product={row} index={index} />
              ))}
            </div>
          </div>
        )
      )}

      {/* Similar listings — the classifieds' way into the feed (Phase 13). */}
      {similar.length > 0 && (
        <div className="mt-16">
          <h2 className="text-2xl font-bold text-gray-900 mb-6">
            {t('similarListings')}
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {similar.slice(0, 4).map((row, index) => (
              <ProductCard key={row.id} product={row} index={index} />
            ))}
          </div>
        </div>
      )}

      {/* Review Modal */}
      <ReviewModal
        isOpen={showReviewModal}
        onClose={() => setShowReviewModal(false)}
        product={product}
        existingReview={userReview}
        onReviewSubmitted={handleReviewSubmitted}
      />
    </div>
  )
}
