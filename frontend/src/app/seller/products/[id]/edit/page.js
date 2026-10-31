'use client'

import { useState, useEffect, useMemo } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { useAuth } from '../../../../../context/AuthContext'
import { productsAPI } from '../../../../../lib/api'
import { apiErrorMessage, apiFieldErrors } from '../../../../../lib/errors'
import {
  effectiveDefinitions,
  fetchCategoryTree,
} from '../../../../../lib/catalog'
import { useTranslations } from 'next-intl'
import {
  ArrowLeft,
  Save,
  AlertCircle,
  CheckCircle,
  Loader2,
} from 'lucide-react'
import Link from 'next/link'
import CategoryPicker from '../../../../../components/common/CategoryPicker'
import AttributeFields from '../../../../../components/product/AttributeFields'
import ImageUploader from '../../../../../components/media/ImageUploader'

export default function EditProductPage() {
  const router = useRouter()
  const params = useParams()
  const productId = params.id
  const t = useTranslations('seller')
  const { isAuthenticated, isSeller, loading: authLoading } = useAuth()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [categoryId, setCategoryId] = useState(null)
  const [attributes, setAttributes] = useState({})
  const [attributeErrors, setAttributeErrors] = useState({})
  const [images, setImages] = useState([])
  // Bumped when the category tree lands — see `definitions` below.
  const [treeVersion, setTreeVersion] = useState(0)
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
      return
    }

    if (isAuthenticated && isSeller && productId) {
      fetchProduct()
    }
  }, [authLoading, isAuthenticated, isSeller, productId])

  // Warm the cached tree on mount (CategoryPicker fetches it too — the
  // cache makes that a no-op), so the dynamic fields re-render when it
  // arrives even if the product request already resolved.
  useEffect(() => {
    let cancelled = false
    fetchCategoryTree()
      .then(() => {
        if (!cancelled) setTreeVersion((version) => version + 1)
      })
      .catch(() => {
        // The picker renders its own load error; the form still works
        // without attribute fields.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const fetchProduct = async () => {
    try {
      setLoading(true)
      // Try seller endpoint first, fallback to public endpoint
      let response
      try {
        response = await productsAPI.getById(productId)
      } catch (err) {
        // Fallback to public endpoint
        response = await productsAPI.get(productId)
      }
      const product = response.data

      setFormData({
        name: product.name || '',
        description: product.description || '',
        base_price: product.base_price || '',
        is_available:
          product.is_available !== undefined ? product.is_available : true,
        low_stock_threshold: product.low_stock_threshold || 5,
      })
      // Phase 12: `category` is the nested {id, slug, name} object; the form
      // writes back `category_id`.
      setCategoryId(product.category?.id ?? null)
      setAttributes(product.attributes_json || {})
      // Existing photos come back as uploads (upload_id) or legacy URLs; the
      // uploader round-trips both, and the payload below sends the same ids.
      setImages(
        (product.images || [])
          .map((image) => ({
            upload_id: image.upload_id || undefined,
            image_url: image.image_url || undefined,
            url: image.url,
            thumb_url: image.thumb_url || image.url,
            lqip: image.lqip || '',
            width: image.width,
            height: image.height,
          }))
          .filter((image) => image.upload_id || image.image_url)
      )
    } catch (error) {
      console.error('Error fetching product:', error)
      setMessage({
        type: 'error',
        text: apiErrorMessage(error, t('edit.loadError')),
      })
    } finally {
      setLoading(false)
    }
  }

  // Definitions come from the cached tree (client-side inheritance — see
  // src/lib/catalog.js), so an edit form renders exactly the fields the
  // product's current category asks for. Recomputed when the tree lands:
  // the product request can resolve before it, and a bare read here would
  // then return [] until some unrelated state change re-rendered the page.
  const definitions = useMemo(
    () => effectiveDefinitions(categoryId),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `treeVersion`
    // is the "the tree cache filled" signal: `effectiveDefinitions` reads
    // the module-level cache, not React state, so it can't be a dep itself.
    [categoryId, treeVersion]
  )

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setFormData((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }))
  }

  const handleCategoryChange = (nextId) => {
    // The stored answers are kept: the server re-validates them against the
    // new subtree on submit (ProductCreateUpdateSerializer.validate), and any
    // key the new category doesn't know comes back under
    // details.attributes_json — highlighted below by key.
    setCategoryId(nextId)
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
      setMessage({ type: 'error', text: t('edit.form.requiredError') })
      return
    }
    if (!categoryId) {
      setMessage({ type: 'error', text: t('edit.form.categoryRequired') })
      return
    }

    try {
      setSaving(true)
      setMessage(null)
      setAttributeErrors({})
      await productsAPI.update(productId, {
        ...formData,
        category_id: categoryId,
        attributes_json: attributes,
        images: images.map((image) =>
          image.upload_id
            ? { upload_id: image.upload_id }
            : { image_url: image.image_url }
        ),
      })
      setMessage({ type: 'success', text: t('edit.updated') })
      setTimeout(() => {
        router.push('/seller/products')
      }, 1500)
    } catch (error) {
      console.error('Error updating product:', error)
      const keyErrors = apiFieldErrors(error).attributes_json
      setAttributeErrors(
        keyErrors && !Array.isArray(keyErrors) ? keyErrors : {}
      )
      setMessage({
        type: 'error',
        text: apiErrorMessage(error, t('edit.updateError')),
      })
    } finally {
      setSaving(false)
    }
  }

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
          <p className="text-gray-600">{t('edit.loading')}</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated || !isSeller) {
    return null
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Link
        href="/seller/products"
        className="inline-flex items-center text-gray-600 hover:text-primary mb-6"
      >
        <ArrowLeft className="h-4 w-4 me-2" />
        {t('edit.back')}
      </Link>

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">
          {t('edit.title')}
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
              {t('edit.form.name')} <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              id="name"
              name="name"
              value={formData.name}
              onChange={handleChange}
              required
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-primary"
              placeholder={t('edit.form.namePlaceholder')}
            />
          </div>

          <div>
            <label
              htmlFor="description"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              {t('edit.form.description')}{' '}
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
              placeholder={t('edit.form.descriptionPlaceholder')}
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
                {t('edit.form.price')} <span className="text-red-500">*</span>
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
                {t('edit.form.category')}{' '}
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
                {t('edit.form.attributesTitle')}
              </h2>
              <p className="text-sm text-gray-500 mb-4">
                {t('edit.form.attributesHint')}
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
              {t('edit.form.lowStock')}
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
              {t('edit.form.lowStockHint')}
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
              {t('edit.form.availability')}
            </label>
          </div>

          <div className="flex gap-4 pt-6 border-t">
            <button
              type="submit"
              disabled={saving}
              className="btn-primary flex items-center gap-2 disabled:opacity-50"
            >
              {saving ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  {t('edit.form.submitting')}
                </>
              ) : (
                <>
                  <Save className="h-5 w-5" />
                  {t('edit.form.submit')}
                </>
              )}
            </button>
            <Link
              href="/seller/products"
              className="px-6 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              {t('edit.cancel')}
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}
