'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { productsAPI, cartAPI, reviewsAPI, wishlistAPI } from '../../../lib/api'
import { useAuth } from '../../../context/AuthContext'
import {
  ShoppingCart,
  Store,
  Package,
  AlertCircle,
  CheckCircle,
  Heart,
  Star,
  MessageSquare,
} from 'lucide-react'
import Link from 'next/link'
import ReviewModal from '../../../components/product/ReviewModal'
import toast from 'react-hot-toast'

export default function ProductDetailPage() {
  const params = useParams()
  const router = useRouter()
  const { isAuthenticated, isSeller } = useAuth()
  const [product, setProduct] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedImage, setSelectedImage] = useState(0)
  const [quantity, setQuantity] = useState(1)
  const [selectedAttributes, setSelectedAttributes] = useState({})
  const [addingToCart, setAddingToCart] = useState(false)
  const [cartMessage, setCartMessage] = useState(null)
  const [isWishlisted, setIsWishlisted] = useState(false)
  const [wishlistLoading, setWishlistLoading] = useState(false)
  const [showReviewModal, setShowReviewModal] = useState(false)
  const [userReview, setUserReview] = useState(null)

  useEffect(() => {
    if (params.id) {
      fetchProduct()
      if (isAuthenticated) {
        checkWishlistStatus()
        checkUserReview()
      }
    }
  }, [params.id, isAuthenticated])

  const fetchProduct = async () => {
    try {
      setLoading(true)
      const response = await productsAPI.get(params.id)
      setProduct(response.data)
    } catch (error) {
      console.error('Error fetching product:', error)
    } finally {
      setLoading(false)
    }
  }

  const checkWishlistStatus = async () => {
    try {
      const response = await wishlistAPI.check(params.id)
      setIsWishlisted(response.data.is_wishlisted)
    } catch (error) {
      console.error('Error checking wishlist:', error)
    }
  }

  const checkUserReview = async () => {
    try {
      const response = await reviewsAPI.checkUserReview(params.id)
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
        await wishlistAPI.remove(params.id)
        setIsWishlisted(false)
        toast.success('Removed from wishlist')
      } else {
        await wishlistAPI.add(params.id)
        setIsWishlisted(true)
        toast.success('Added to wishlist')
      }
    } catch (error) {
      console.error('Error toggling wishlist:', error)
      toast.error('Failed to update wishlist')
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
        text: 'Sellers cannot add products to cart',
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
      setCartMessage({ type: 'success', text: 'Product added to cart!' })
      setTimeout(() => setCartMessage(null), 3000)
    } catch (error) {
      setCartMessage({
        type: 'error',
        text: error.response?.data?.error || 'Failed to add to cart',
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
        <p className="text-gray-500 text-lg">Product not found</p>
        <Link
          href="/products"
          className="text-primary hover:text-secondary mt-4 inline-block"
        >
          Back to Products
        </Link>
      </div>
    )
  }

  const images = product.images || []
  const mainImage =
    images[selectedImage]?.image_url || '/placeholder-product.jpg'

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Breadcrumb */}
      <nav className="mb-4 text-sm">
        <Link href="/" className="text-gray-500 hover:text-primary">
          Home
        </Link>
        <span className="mx-2 text-gray-400">/</span>
        <Link href="/products" className="text-gray-500 hover:text-primary">
          Products
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
            <CheckCircle className="h-5 w-5 mr-2 flex-shrink-0" />
          ) : (
            <AlertCircle className="h-5 w-5 mr-2 flex-shrink-0" />
          )}
          <span>{cartMessage.text}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Images */}
        <div>
          <div className="bg-gray-100 rounded-lg overflow-hidden mb-4 aspect-square">
            <img
              src={mainImage}
              alt={product.name}
              className="w-full h-full object-cover"
              onError={(e) => {
                e.target.src = '/placeholder-product.jpg'
              }}
            />
          </div>
          {images.length > 1 && (
            <div className="grid grid-cols-4 gap-2">
              {images.map((img, index) => (
                <button
                  key={index}
                  onClick={() => setSelectedImage(index)}
                  className={`border-2 rounded-lg overflow-hidden transition-all ${
                    selectedImage === index
                      ? 'border-primary ring-2 ring-primary'
                      : 'border-gray-300'
                  }`}
                >
                  <img
                    src={img.image_url}
                    alt={`${product.name} ${index + 1}`}
                    className="w-full h-20 object-cover"
                    onError={(e) => {
                      e.target.src = '/placeholder-product.jpg'
                    }}
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Product Info */}
        <div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            {product.name}
          </h1>

          <Link
            href={`/stores/${product.store?.store_slug}`}
            className="flex items-center text-gray-600 hover:text-primary mb-4 w-fit"
          >
            <Store className="h-4 w-4 mr-1" />
            <span className="text-sm">{product.store?.store_name}</span>
          </Link>

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
              <span className="ml-2 text-sm text-gray-600">
                {product.average_rating
                  ? product.average_rating.toFixed(1)
                  : '0.0'}
                ({product.review_count || 0}{' '}
                {product.review_count === 1 ? 'review' : 'reviews'})
              </span>
            </div>
          </div>

          {product.category && (
            <span className="inline-block mb-4 text-xs bg-blue-100 text-primary px-3 py-1 rounded-full">
              {product.category}
            </span>
          )}

          <div className="text-4xl font-bold text-primary mb-6">
            ${parseFloat(product.base_price).toFixed(2)}
          </div>

          <div className="mb-6 pb-6 border-b">
            <h2 className="text-lg font-semibold mb-2">Description</h2>
            <p className="text-gray-600 whitespace-pre-wrap">
              {product.description}
            </p>
          </div>

          {product.attributes && product.attributes.length > 0 && (
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-3">Options</h3>
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
                      <option value="">Select {attr.attribute_name}</option>
                      <option value={attr.attribute_value}>
                        {attr.attribute_value}
                      </option>
                    </select>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Quantity
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
              {product.is_available ? 'In Stock' : 'Out of Stock'}
            </span>
          </div>

          <div className="flex gap-3 mb-6">
            <button
              onClick={handleAddToCart}
              disabled={!product.is_available || addingToCart || isSeller}
              className="flex-1 btn-primary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ShoppingCart className="h-5 w-5" />
              {addingToCart ? 'Adding...' : 'Add to Cart'}
            </button>
            <button
              onClick={toggleWishlist}
              disabled={wishlistLoading}
              className={`p-3 border-2 rounded-lg transition-colors ${
                isWishlisted
                  ? 'border-red-500 text-red-500 hover:bg-red-50'
                  : 'border-gray-300 hover:border-primary hover:text-primary'
              }`}
              title={isWishlisted ? 'Remove from Wishlist' : 'Add to Wishlist'}
            >
              <Heart
                className={`h-6 w-6 ${isWishlisted ? 'fill-red-500' : ''}`}
              />
            </button>
          </div>

          {/* Write Review Button */}
          {isAuthenticated && !isSeller && (
            <button
              onClick={() => setShowReviewModal(true)}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 mb-4"
            >
              <MessageSquare className="h-5 w-5" />
              {userReview ? 'Edit Your Review' : 'Write a Review'}
            </button>
          )}

          {isSeller && (
            <p className="text-sm text-gray-500 text-center">
              Sellers cannot purchase products
            </p>
          )}

          {/* Additional Info */}
          <div className="mt-8 pt-6 border-t">
            <h3 className="text-lg font-semibold mb-3">Product Information</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex">
                <dt className="text-gray-600 w-32">SKU:</dt>
                <dd className="text-gray-900 font-medium">{product.id}</dd>
              </div>
              <div className="flex">
                <dt className="text-gray-600 w-32">Category:</dt>
                <dd className="text-gray-900 font-medium">
                  {product.category || 'General'}
                </dd>
              </div>
              <div className="flex">
                <dt className="text-gray-600 w-32">Availability:</dt>
                <dd
                  className={`font-medium ${
                    product.is_available ? 'text-green-600' : 'text-red-600'
                  }`}
                >
                  {product.is_available ? 'In Stock' : 'Out of Stock'}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </div>

      {/* Reviews Section */}
      <div className="mt-16 border-t pt-8">
        <h2 className="text-2xl font-bold text-gray-900 mb-6">
          Customer Reviews ({product.review_count || 0})
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
                      {new Date(review.created_at).toLocaleDateString()}
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
            <p className="text-gray-600 mb-2">No reviews yet</p>
            <p className="text-sm text-gray-500">
              Be the first to review this product
            </p>
          </div>
        )}
      </div>

      {/* Related Products Section */}
      <div className="mt-16">
        <h2 className="text-2xl font-bold text-gray-900 mb-6">
          More from this store
        </h2>
        <Link
          href={`/stores/${product.store?.store_slug}`}
          className="text-primary hover:text-secondary"
        >
          View all products from {product.store?.store_name} →
        </Link>
      </div>

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
