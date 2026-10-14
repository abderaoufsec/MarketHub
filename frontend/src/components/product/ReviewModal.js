'use client'

import { useState } from 'react'
import { reviewsAPI } from '../../lib/api'
import { apiErrorMessage } from '../../lib/errors'
import { Star, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { useTranslations } from 'next-intl'
import { usePrice } from '../../lib/currency'

const RATING_LABEL_KEYS = {
  1: 'poor',
  2: 'fair',
  3: 'good',
  4: 'veryGood',
  5: 'excellent',
}

export default function ReviewModal({
  isOpen,
  onClose,
  product,
  existingReview,
  onReviewSubmitted,
}) {
  const t = useTranslations('products')
  const price = usePrice()
  const [rating, setRating] = useState(existingReview?.rating || 0)
  const [comment, setComment] = useState(existingReview?.comment || '')
  const [hoveredRating, setHoveredRating] = useState(0)
  const [submitting, setSubmitting] = useState(false)

  if (!isOpen) return null

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (rating === 0) {
      toast.error(t('selectRating'))
      return
    }

    if (!comment.trim()) {
      toast.error(t('writeComment'))
      return
    }

    setSubmitting(true)

    try {
      if (existingReview) {
        // Update existing review
        await reviewsAPI.update(existingReview.id, {
          rating,
          comment,
          product: product.id,
        })
        toast.success(t('updateSuccess'))
      } else {
        // Create new review
        await reviewsAPI.create({ product: product.id, rating, comment })
        toast.success(t('submitSuccess'))
      }

      onReviewSubmitted()
      onClose()
    } catch (error) {
      console.error('Error submitting review:', error)
      toast.error(apiErrorMessage(error, t('submitError')))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm(t('deleteConfirm'))) {
      return
    }

    setSubmitting(true)
    try {
      await reviewsAPI.delete(existingReview.id)
      toast.success(t('deleteSuccess'))
      onReviewSubmitted()
      onClose()
    } catch (error) {
      console.error('Error deleting review:', error)
      toast.error(t('deleteError'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold text-gray-900">
              {existingReview ? t('editReview') : t('writeReview')}
            </h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600"
              aria-label={t('close')}
            >
              <X className="h-6 w-6" />
            </button>
          </div>

          {/* Product Info */}
          <div className="flex items-center gap-4 mb-6 p-4 bg-gray-50 rounded-lg">
            <img
              src={product.images?.[0]?.image_url || '/placeholder-product.jpg'}
              alt={product.name}
              className="w-16 h-16 object-cover rounded"
            />
            <div>
              <h3 className="font-semibold text-gray-900">{product.name}</h3>
              <p className="text-sm text-gray-600">
                {price(product.base_price)}
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit}>
            {/* Rating */}
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('yourRating')}
              </label>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    type="button"
                    onMouseEnter={() => setHoveredRating(star)}
                    onMouseLeave={() => setHoveredRating(0)}
                    onClick={() => setRating(star)}
                    className="focus:outline-none"
                  >
                    <Star
                      className={`h-8 w-8 ${
                        star <= (hoveredRating || rating)
                          ? 'fill-yellow-400 text-yellow-400'
                          : 'text-gray-300'
                      } transition-colors`}
                    />
                  </button>
                ))}
              </div>
              {rating > 0 && (
                <p className="text-sm text-gray-600 mt-2">
                  {t(`ratings.${RATING_LABEL_KEYS[rating]}`)}
                </p>
              )}
            </div>

            {/* Comment */}
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('yourReview')}
              </label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={6}
                className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:ring-primary focus:border-primary"
                placeholder={t('commentPlaceholder')}
                required
              />
              <p className="text-xs text-gray-500 mt-1">{t('minCharacters')}</p>
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                type="submit"
                disabled={
                  submitting || rating === 0 || comment.trim().length < 10
                }
                className="flex-1 btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting
                  ? t('submitting')
                  : existingReview
                    ? t('updateReview')
                    : t('submitReview')}
              </button>

              {existingReview && (
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={submitting}
                  className="px-4 py-2 border border-red-300 text-red-600 rounded-lg hover:bg-red-50 disabled:opacity-50"
                >
                  {t('delete')}
                </button>
              )}

              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                {t('cancel')}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
