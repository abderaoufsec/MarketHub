'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import toast from 'react-hot-toast'
import {
  Tag,
  ImagePlus,
  ListChecks,
  MapPin,
  BadgeDollarSign,
  ChevronLeft,
  ChevronRight,
  Send,
  Check,
  AlertTriangle,
  X,
  Loader2,
} from 'lucide-react'
import { productsAPI } from '../../lib/api'
import { apiErrorMessage } from '../../lib/errors'
import { effectiveDefinitions } from '../../lib/catalog'
import { useAuth } from '../../context/AuthContext'
import CategoryPicker from '../../components/common/CategoryPicker'
import LocationPicker from '../../components/common/LocationPicker'
import AttributeFields from '../../components/product/AttributeFields'

/**
 * The fast-posting wizard (Phase 13 of docs/todo.md): "anyone can post in
 * under 90 seconds". Five steps, each one a screen of decisions instead of a
 * wall of fields:
 *
 *   1. what it is (type + category) — 2. photos — 3. details (the category's
 *   dynamic fields + how buyers reach you) — 4. where — 5. price & publish.
 *
 * Every step boundary autosaves (POST /products/create/ once, then PATCH
 * /products/seller/<id>/), so a dropped connection, a reload or a call that
 * interrupts the session never costs the seller what they typed — on a slow
 * mobile network that *is* the feature.
 *
 * Publishing walks the API's lifecycle: `possible_duplicate` (same ad posted
 * twice) surfaces as an inline confirm — "publish anyway?" retries with
 * `allow_duplicate: true`, which can never bypass completeness or quota.
 * `incomplete_listing` jumps back to the step that owns the missing field.
 */

const STEPS = ['basics', 'photos', 'details', 'location', 'publish']

// Server-validated (MAX_IMAGES_PER_LISTING); mirrored here so the form
// stops before an error the seller cannot act on.
const MAX_IMAGES = 15

const LISTING_TYPES = ['FOR_SALE', 'SERVICE', 'JOB', 'RENT', 'WANTED']
const PRICE_MODES = ['FIXED', 'NEGOTIABLE', 'ON_REQUEST', 'FREE', 'EXCHANGE']
const CONTACT_MODES = ['PHONE', 'WHATSAPP', 'CHAT', 'CHECKOUT']

const STEP_ICONS = {
  basics: Tag,
  photos: ImagePlus,
  details: ListChecks,
  location: MapPin,
  publish: BadgeDollarSign,
}

/** Which step owns each backend field of `incomplete_listing.details.missing`. */
function stepForMissingField(field) {
  if (['name', 'description', 'category'].includes(field)) return 0
  if (field === 'images') return 1
  if (['attributes_json', 'contact_mode'].includes(field)) return 2
  if (['wilaya', 'commune'].includes(field)) return 3
  if (['base_price', 'price_mode', 'old_price'].includes(field)) return 4
  return null
}

export default function PostListingPage() {
  const t = useTranslations('post')
  const router = useRouter()
  const { isAuthenticated, loading: authLoading } = useAuth()

  const [step, setStep] = useState(0)
  const [draftId, setDraftId] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [duplicate, setDuplicate] = useState(null)
  const [quota, setQuota] = useState(null)
  const [attributeErrors, setAttributeErrors] = useState({})
  const [imageUrl, setImageUrl] = useState('')
  const [form, setForm] = useState({
    listing_type: 'FOR_SALE',
    name: '',
    description: '',
    categoryId: null,
    images: [],
    attributes: {},
    contactMode: 'PHONE',
    wilayaId: null,
    communeId: null,
    priceMode: 'FIXED',
    basePrice: '',
    oldPrice: '',
  })

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.replace('/login?next=/post')
    }
  }, [authLoading, isAuthenticated, router])

  useEffect(() => {
    if (!isAuthenticated) return
    productsAPI
      .quota()
      .then((response) => setQuota(response.data))
      .catch(() => {})
  }, [isAuthenticated])

  const setField = (patch) => {
    setForm((current) => ({ ...current, ...patch }))
    setSaved(false)
  }

  // The category's effective attributes (own + ancestors', deeper winning),
  // resolved client-side from the cached tree — switching category swaps the
  // visible fields with no refetch. Picking a *different* category drops the
  // previous answers: they may not even be keys in the new subtree.
  const definitions = effectiveDefinitions(form.categoryId)

  const draftPayload = useCallback(() => {
    const data = {
      listing_type: form.listing_type,
      name: form.name.trim(),
      description: form.description.trim(),
      attributes_json: form.attributes,
      contact_mode: form.contactMode,
      price_mode: form.priceMode,
    }
    if (form.categoryId) data.category_id = form.categoryId
    if (form.images.length) data.images = form.images
    if (form.wilayaId) data.wilaya_id = form.wilayaId
    if (form.communeId) data.commune_id = form.communeId
    if (form.basePrice !== '') data.base_price = form.basePrice
    if (form.oldPrice !== '') data.old_price = form.oldPrice
    return data
  }, [form])

  /**
   * Autosave the draft as it stands. Returns false only when the server
   * refused the save — the wizard still advances on nothing.
   */
  const saveDraft = async () => {
    const payload = draftPayload()
    setSaving(true)
    try {
      if (draftId) {
        await productsAPI.updateListing(draftId, payload)
      } else {
        const response = await productsAPI.createListing(payload)
        setDraftId(response.data.id)
      }
      setSaved(true)
      return true
    } catch (error) {
      const code = error.response?.data?.code
      if (code === 'draft_limit') {
        toast.error(t('errors.draftLimit'))
      } else if (code === 'invalid_attributes') {
        setAttributeErrors(error.response?.data?.details?.errors || {})
        toast.error(apiErrorMessage(error, t('errors.generic')))
        setStep(2)
      } else if (code === 'wrong_listing_type') {
        toast.error(t('errors.wrongListingType'))
      } else {
        toast.error(apiErrorMessage(error, t('errors.saveFailed')))
      }
      return false
    } finally {
      setSaving(false)
    }
  }

  const goNext = async () => {
    if (step === 0 && !form.name.trim()) {
      toast.error(t('errors.nameRequired'))
      return
    }
    if (step === 0 && !form.categoryId) {
      toast.error(t('errors.categoryRequired'))
      return
    }
    const ok = await saveDraft()
    if (!ok) return
    setStep((current) => Math.min(current + 1, STEPS.length - 1))
  }

  const goBack = () => setStep((current) => Math.max(current - 1, 0))

  const publish = async (allowDuplicate = false) => {
    // One last save: the price fields are step 5, typed after the previous
    // autosave — publishing stale values would be a lie.
    const ok = await saveDraft()
    if (!ok) return
    setPublishing(true)
    try {
      const response = await productsAPI.lifecycle(
        draftId,
        'publish',
        allowDuplicate ? { allow_duplicate: true } : {}
      )
      toast.success(t('published'))
      router.push(response.data.canonical_path || `/l/_-${draftId}`)
    } catch (error) {
      const code = error.response?.data?.code
      const details = error.response?.data?.details || {}
      if (code === 'possible_duplicate') {
        setDuplicate({
          id: details.duplicate_of,
          name: details.duplicate_name,
        })
      } else if (code === 'incomplete_listing') {
        toast.error(
          t('errors.incomplete', { fields: (details.missing || []).join(', ') })
        )
        const firstMissing = (details.missing || [])
          .map(stepForMissingField)
          .find((index) => index !== null)
        if (firstMissing !== undefined) setStep(firstMissing)
      } else if (code === 'invalid_attributes') {
        setAttributeErrors(details.errors || {})
        toast.error(apiErrorMessage(error, t('errors.attributesInvalid')))
        setStep(2)
      } else if (code === 'quota_reached') {
        toast.error(
          t('errors.quotaReached', {
            quota: details.quota,
            active: details.active,
          })
        )
      } else {
        toast.error(apiErrorMessage(error, t('errors.generic')))
      }
    } finally {
      setPublishing(false)
    }
  }

  const addImage = () => {
    const url = imageUrl.trim()
    if (!url) return
    if (!/^https?:\/\//.test(url)) {
      toast.error(t('errors.imageUrl'))
      return
    }
    if (form.images.length >= MAX_IMAGES) {
      toast.error(t('errors.maxImages', { max: MAX_IMAGES }))
      return
    }
    setField({ images: [...form.images, { image_url: url }] })
    setImageUrl('')
  }

  const removeImage = (index) => {
    setField({ images: form.images.filter((_, i) => i !== index) })
  }

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  const stepKey = STEPS[step]
  const isLast = step === STEPS.length - 1

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-1">
          {t('heading')}
        </h1>
        <p className="text-gray-600">{t('subtitle')}</p>
        {quota && (
          <p className="text-sm text-gray-500 mt-2 flex items-center gap-1">
            <Check className="h-4 w-4 text-green-600" />
            {quota.listing_quota == null
              ? t('quota.unlimited')
              : t('quota.active', {
                  used: quota.active_listings,
                  limit: quota.listing_quota,
                })}{' '}
            ·{' '}
            {t('quota.drafts', {
              drafts: quota.drafts,
              draftLimit: quota.draft_limit,
            })}
          </p>
        )}
      </div>

      {/* Step progress */}
      <ol className="flex items-center gap-2 mb-8">
        {STEPS.map((key, index) => {
          const Icon = STEP_ICONS[key]
          const active = index === step
          const done = index < step
          return (
            <li key={key} className="flex-1">
              <button
                type="button"
                onClick={() => index < step && setStep(index)}
                disabled={index > step}
                className={`w-full flex items-center justify-center gap-2 py-2 px-1 rounded-lg text-sm border transition-colors ${
                  active
                    ? 'border-primary text-primary bg-primary/5'
                    : done
                      ? 'border-green-200 text-green-700 hover:bg-green-50'
                      : 'border-gray-200 text-gray-400'
                } ${index < step ? 'cursor-pointer' : 'cursor-default'}`}
              >
                <Icon className="h-4 w-4 flex-shrink-0" />
                <span className="hidden sm:inline">{t(`steps.${key}`)}</span>
              </button>
            </li>
          )
        })}
      </ol>

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        {/* ---- Step 1: what it is ---- */}
        {stepKey === 'basics' && (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('fields.type')} *
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {LISTING_TYPES.map((type) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setField({ listing_type: type })}
                    className={`px-3 py-2 rounded-lg border text-sm transition-colors ${
                      form.listing_type === type
                        ? 'border-primary text-primary bg-primary/5 font-medium'
                        : 'border-gray-300 text-gray-700 hover:border-primary'
                    }`}
                  >
                    {t(`types.${type}`)}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label
                htmlFor="post-name"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                {t('fields.name')} *
              </label>
              <input
                id="post-name"
                type="text"
                value={form.name}
                onChange={(e) => setField({ name: e.target.value })}
                placeholder={t('placeholders.name')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                maxLength={255}
              />
            </div>
            <div>
              <label
                htmlFor="post-description"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                {t('fields.description')} *
              </label>
              <textarea
                id="post-description"
                value={form.description}
                onChange={(e) => setField({ description: e.target.value })}
                placeholder={t('placeholders.description')}
                rows={4}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
              />
            </div>
            <div>
              <label
                htmlFor="post-category"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                {t('fields.category')} *
              </label>
              <CategoryPicker
                categoryId={form.categoryId}
                onChange={(id) => setField({ categoryId: id, attributes: {} })}
                required
                id="post-category"
              />
            </div>
          </div>
        )}

        {/* ---- Step 2: photos ---- */}
        {stepKey === 'photos' && (
          <div className="space-y-4">
            <p className="text-sm text-gray-600">{t('photosHint')}</p>
            <div className="flex gap-2">
              <input
                type="url"
                aria-label={t('fields.photoUrl')}
                value={imageUrl}
                onChange={(e) => setImageUrl(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addImage()
                  }
                }}
                placeholder={t('placeholders.imageUrl')}
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
              />
              <button
                type="button"
                onClick={addImage}
                className="btn-primary flex items-center gap-2"
              >
                <ImagePlus className="h-4 w-4" />
                {t('addImage')}
              </button>
            </div>
            {form.images.length > 0 && (
              <ul className="grid grid-cols-3 sm:grid-cols-4 gap-3">
                {form.images.map((image, index) => (
                  <li
                    key={`${image.image_url}-${index}`}
                    className="relative border border-gray-200 rounded-lg overflow-hidden group"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={image.image_url}
                      alt=""
                      className="w-full h-24 object-cover"
                      onError={(e) => {
                        e.target.src = '/placeholder-product.jpg'
                      }}
                    />
                    {index === 0 && (
                      <span className="absolute bottom-1 start-1 text-xs bg-black/60 text-white px-2 py-0.5 rounded-full">
                        {t('primaryPhoto')}
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => removeImage(index)}
                      aria-label={t('removeImage')}
                      className="absolute top-1 end-1 p-1 bg-white/90 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <X className="h-3 w-3 text-red-600" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* ---- Step 3: details ---- */}
        {stepKey === 'details' && (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('fields.contactMode')}
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {CONTACT_MODES.map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setField({ contactMode: mode })}
                    className={`px-3 py-2 rounded-lg border text-sm transition-colors ${
                      form.contactMode === mode
                        ? 'border-primary text-primary bg-primary/5 font-medium'
                        : 'border-gray-300 text-gray-700 hover:border-primary'
                    }`}
                  >
                    {t(`contactModes.${mode}`)}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-2">
                {t('contactModeHint')}
              </p>
            </div>
            <div>
              <h3 className="text-sm font-medium text-gray-700 mb-2">
                {t('fields.details')}
              </h3>
              <AttributeFields
                definitions={definitions}
                values={form.attributes}
                errors={attributeErrors}
                onChange={(key, value) =>
                  setField({
                    attributes: { ...form.attributes, [key]: value },
                  })
                }
              />
              {definitions.length === 0 && (
                <p className="text-sm text-gray-500">{t('noAttributes')}</p>
              )}
            </div>
          </div>
        )}

        {/* ---- Step 4: where ---- */}
        {stepKey === 'location' && (
          <div className="space-y-4">
            <p className="text-sm text-gray-600">{t('locationHint')}</p>
            <LocationPicker
              wilayaId={form.wilayaId}
              communeId={form.communeId}
              onChange={({ wilayaId, communeId }) =>
                setField({ wilayaId, communeId })
              }
              required
            />
          </div>
        )}

        {/* ---- Step 5: price & publish ---- */}
        {stepKey === 'publish' && (
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('fields.priceMode')}
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                {PRICE_MODES.map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setField({ priceMode: mode })}
                    className={`px-3 py-2 rounded-lg border text-sm transition-colors ${
                      form.priceMode === mode
                        ? 'border-primary text-primary bg-primary/5 font-medium'
                        : 'border-gray-300 text-gray-700 hover:border-primary'
                    }`}
                  >
                    {t(`priceModes.${mode}`)}
                  </button>
                ))}
              </div>
            </div>
            {form.priceMode !== 'ON_REQUEST' && form.priceMode !== 'FREE' && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label
                    htmlFor="post-price"
                    className="block text-sm font-medium text-gray-700 mb-2"
                  >
                    {t('fields.price')} *
                  </label>
                  <input
                    id="post-price"
                    type="number"
                    min="0"
                    step="0.01"
                    value={form.basePrice}
                    onChange={(e) => setField({ basePrice: e.target.value })}
                    placeholder="15000"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                  />
                </div>
                {form.priceMode === 'FIXED' && (
                  <div>
                    <label
                      htmlFor="post-old-price"
                      className="block text-sm font-medium text-gray-700 mb-2"
                    >
                      {t('fields.oldPrice')}
                    </label>
                    <input
                      id="post-old-price"
                      type="number"
                      min="0"
                      step="0.01"
                      value={form.oldPrice}
                      onChange={(e) => setField({ oldPrice: e.target.value })}
                      placeholder="20000"
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-primary focus:border-primary"
                    />
                  </div>
                )}
              </div>
            )}

            {duplicate && (
              <div className="rounded-lg border border-yellow-300 bg-yellow-50 p-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="h-5 w-5 text-yellow-700 flex-shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <p className="text-sm text-yellow-800 font-medium">
                      {t('duplicateWarning', { name: duplicate.name })}
                    </p>
                    <div className="flex gap-2 mt-3">
                      <button
                        type="button"
                        onClick={() => publish(true)}
                        disabled={publishing}
                        className="btn-primary text-sm flex items-center gap-1 disabled:opacity-50"
                      >
                        {publishing ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Send className="h-4 w-4" />
                        )}
                        {t('publishAnyway')}
                      </button>
                      <Link
                        href={`/l/_-${duplicate.id}`}
                        className="text-sm px-3 py-1 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
                      >
                        {t('viewExisting')}
                      </Link>
                      <button
                        type="button"
                        onClick={() => setDuplicate(null)}
                        className="text-sm px-3 py-1 text-gray-600 hover:text-gray-800"
                      >
                        {t('dismiss')}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Wizard footer */}
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={goBack}
          disabled={step === 0 || saving}
          className="flex items-center gap-1 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <ChevronLeft className="h-4 w-4" />
          {t('back')}
        </button>

        <span className="text-xs text-gray-500 flex items-center gap-1">
          {saving ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" />
              {t('saving')}
            </>
          ) : saved && draftId ? (
            <>
              <Check className="h-3 w-3 text-green-600" />
              {t('saved')}
            </>
          ) : null}
        </span>

        {isLast ? (
          <button
            type="button"
            onClick={() => publish(false)}
            disabled={publishing || saving}
            className="btn-primary flex items-center gap-2 disabled:opacity-50"
          >
            {publishing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            {t('publish')}
          </button>
        ) : (
          <button
            type="button"
            onClick={goNext}
            disabled={saving}
            className="btn-primary flex items-center gap-2 disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
            {t('continue')}
          </button>
        )}
      </div>
    </div>
  )
}
