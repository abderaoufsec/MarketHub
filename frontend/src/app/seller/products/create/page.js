'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../../../../context/AuthContext'
import { productsAPI } from '../../../../lib/api'
import { apiErrorMessage, apiFieldErrors } from '../../../../lib/errors'
import { effectiveDefinitions } from '../../../../lib/catalog'
import { useTranslations } from 'next-intl'
import { ArrowLeft, Save, AlertCircle, CheckCircle } from 'lucide-react'
import Link from 'next/link'
import CategoryPicker from '../../../../components/common/CategoryPicker'
import AttributeFields from '../../../../components/product/AttributeFields'
import ImageUploader from '../../../../components/media/ImageUploader'

export default function CreateProductPage() {
  const router = useRouter()
  const t = useTranslations('seller')
  const { isAuthenticated, isSeller, loading: authLoading } = useAuth()
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)
  const [categoryId, setCategoryId] = useState(null)
  const [attributes, setAttributes] = useState({})
  const [attributeErrors, setAttributeErrors] = useState({})
  const [images, setImages] = useState([])
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    base_price: '',
    is_available: true,
    low_stock_threshold: 5,
  })

  useEffect(() => {
    if (!authLoading && (!isAuthenticated || !isSeller)) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, isSeller, router])

  // Definitions come from the cached tree (client-side inheritance — see
  // src/lib/catalog.js): switching category swaps the visible fields with
  // no refetch, and the previous category's answers are dropped because
  // they may not even be keys in the new subtree.
  const definitions = effectiveDefinitions(categoryId)

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setFormData((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }))
  }

  const handleCategoryChange = (nextId) => {
    setCategoryId(nextId)
    setAttributes({})
    setAttributeErrors({})
  }

  const handleAttributeChange = (key, value) => {
    setAttributeErrors((prev) => {
      if (!prev[key]) return prev
      const { [key]: _dropped, ...rest } = prev
      return rest
    })
    setAttributes((prev) => ({ ...prev, [key]: value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!formData.name || !formData.description || !formData.base_price) {
      setMessage({ type: 'error', text: t('create.form.requiredError') })
      return
    }
    if (!categoryId) {
      setMessage({ type: 'error', text: t('create.form.categoryRequired') })
      return
    }

    try {
      setLoading(true)
      setMessage(null)
      setAttributeErrors({})
      // Blank answers (null / empty range) are dropped server-side; sending
      // them is harmless and keeps this payload a plain diff of the form.
      await productsAPI.create({
        ...formData,
        category_id: categoryId,
        attributes_json: attributes,
        images: images.map((image) =>
          image.upload_id
            ? { upload_id: image.upload_id }
            : { image_url: image.image_url }
        ),
      })
      setMessage({ type: 'success', text: t('create.created') })
      setTimeout(() => {
        router.push('/seller/products')
      }, 1500)
    } catch (error) {
      console.error('Error creating product:', error)
      // Per-key attribute messages highlight the offending inputs (Phase 12
      // contract: details.attributes_json.{key}).
      const keyErrors = apiFieldErrors(error).attributes_json
      setAttributeErrors(
        keyErrors && !Array.isArray(keyErrors) ? keyErrors : {}
      )
      setMessage({
        type: 'error',
        text: apiErrorMessage(error, t('create.createError')),
      })
    } finally {
      setLoading(false)
    }
  }

  if (authLoading || !isAuthenticated || !isSeller) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Link
        href="/seller/products"
        className="inline-flex items-center text-gray-600 hover:text-primary mb-6"
      >
        <ArrowLeft className="h-4 w-4 me-2" />
        {t('create.back')}
      </Link>

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">
          {t('create.title')}
        </h1>

        {message && (
          <div
            className={`mb-6 p-4 rounded-lg flex items-center ${
              message.type === 'success'
                ? 'bg-green-50 border border-green-200 text-green-700'
                : 'bg-red-50 border border-red-200 text-red-700'
            }`}
          >
            {message.type === 'success' ? (
              <CheckCircle className="h-5 w-5 me-2 flex-shrink-0" />
            ) : (
              <AlertCircle className="h-5 w-5 me-2 flex-shrink-0" />
            )}
            <span>{message.text}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label
              htmlFor="name"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              {t('create.form.name')} <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              id="name"
              name="name"
              value={formData.name}
              onChange={handleChange}
              required
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
              placeholder={t('create.form.namePlaceholder')}
            />
          </div>

          <div>
            <label
              htmlFor="description"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              {t('create.form.description')}{' '}
              <span className="text-red-500">*</span>
            </label>
            <textarea
              id="description"
              name="description"
              value={formData.description}
              onChange={handleChange}
              required
              rows={4}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
              placeholder={t('create.form.descriptionPlaceholder')}
            />
          </div>

          <div className="border-t border-gray-100 pt-6">
            <ImageUploader images={images} onChange={setImages} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label
                htmlFor="base_price"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                {t('create.form.price')} <span className="text-red-500">*</span>
              </label>
              <input
                type="number"
                id="base_price"
                name="base_price"
                value={formData.base_price}
                onChange={handleChange}
                required
                step="0.01"
                min="0"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
                placeholder="0.00"
              />
            </div>

            <div>
              <label
                htmlFor="category-picker"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                {t('create.form.category')}{' '}
                <span className="text-red-500">*</span>
              </label>
              <CategoryPicker
                id="category-picker"
                categoryId={categoryId}
                onChange={handleCategoryChange}
                required
              />
            </div>
          </div>

          {definitions.length > 0 && (
            <div className="border-t border-gray-100 pt-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">
                {t('create.form.attributesTitle')}
              </h2>
              <p className="text-sm text-gray-500 mb-4">
                {t('create.form.attributesHint')}
              </p>
              <AttributeFields
                definitions={definitions}
                values={attributes}
                errors={attributeErrors}
                onChange={handleAttributeChange}
              />
            </div>
          )}

          <div>
            <label
              htmlFor="low_stock_threshold"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              {t('create.form.lowStock')}
            </label>
            <input
              type="number"
              id="low_stock_threshold"
              name="low_stock_threshold"
              value={formData.low_stock_threshold}
              onChange={handleChange}
              min="0"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
              placeholder="5"
            />
            <p className="text-sm text-gray-500 mt-1">
              {t('create.form.lowStockHint')}
            </p>
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="is_available"
              name="is_available"
              checked={formData.is_available}
              onChange={handleChange}
              className="h-4 w-4 text-primary focus:ring-primary border-gray-300 rounded"
            />
            <label
              htmlFor="is_available"
              className="ms-2 block text-sm text-gray-700"
            >
              {t('create.form.availability')}
            </label>
          </div>

          <div className="flex gap-4 pt-6 border-t">
            <button
              type="submit"
              disabled={loading}
              className="btn-primary flex items-center gap-2 disabled:opacity-50"
            >
              <Save className="h-5 w-5" />
              {loading ? t('create.form.submitting') : t('create.form.submit')}
            </button>
            <Link
              href="/seller/products"
              className="px-6 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              {t('create.cancel')}
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}
