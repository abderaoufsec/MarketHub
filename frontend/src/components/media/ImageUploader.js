'use client'

import { useEffect, useId, useRef, useState } from 'react'
import { GripVertical, ImagePlus, Loader2, Star, Trash2 } from 'lucide-react'
import { useTranslations } from 'next-intl'
import toast from 'react-hot-toast'

import { mediaAPI } from '../../lib/api'
import {
  ACCEPTED_IMAGE_TYPES,
  compressImage,
  isSupportedImage,
} from '../../lib/imageCompression'

/** The form's shape for one photo: what the API gave us back. */
export function imageEntryFromUpload(data) {
  return {
    upload_id: data.id,
    url: data.card_url || data.url,
    thumb_url: data.thumb_url || data.card_url || data.url,
    lqip: data.lqip || '',
    width: data.width,
    height: data.height,
  }
}

/** The write payload for a photo: an upload, or a legacy external URL. */
export function imageEntryPayload(entry) {
  if (entry.upload_id) return { upload_id: entry.upload_id }
  if (entry.image_url) return { image_url: entry.image_url }
  return null
}

/**
 * Photo picker shared by the posting wizard and the seller forms (Phase 14).
 *
 * Picking is phone-first: the browser compresses each file before it is sent
 * (see `lib/imageCompression`), the upload shows its own progress, and the
 * grid reorders by drag — the first photo is the cover. `onChange` always
 * receives the whole list, so the parent owns the state and the payload.
 */
export default function ImageUploader({
  images = [],
  onChange,
  max = 15,
  disabled = false,
}) {
  const t = useTranslations('media')
  const inputId = useId()
  const inputRef = useRef(null)
  const latest = useRef(images)
  const [uploading, setUploading] = useState([])
  const [dragIndex, setDragIndex] = useState(null)

  useEffect(() => {
    latest.current = images
  }, [images])

  const atLimit = images.length >= max
  const busy = uploading.length > 0

  const emit = (next) => {
    latest.current = next
    onChange(next)
  }

  const setProgress = (key, progress) => {
    setUploading((current) =>
      current.map((row) => (row.key === key ? { ...row, progress } : row))
    )
  }

  const addUpload = (entry) => {
    if (latest.current.length >= max) return
    emit([...latest.current, entry])
  }

  const handleFiles = async (event) => {
    const files = Array.from(event.target.files || [])
    // Reset the input so picking the same file again still fires onChange.
    event.target.value = ''
    if (!files.length) return

    const room = max - latest.current.length
    if (room <= 0) {
      toast.error(t('maxReached', { max }))
      return
    }
    if (files.length > room) toast.error(t('maxReached', { max }))

    for (const file of files.slice(0, room)) {
      if (!isSupportedImage(file)) {
        toast.error(t('errors.unsupported'))
        continue
      }
      const key = `${file.name}-${file.size}-${Math.random().toString(36).slice(2)}`
      setUploading((current) => [
        ...current,
        { key, name: file.name, progress: 0 },
      ])
      try {
        const compressed = await compressImage(file)
        const response = await mediaAPI.upload(compressed, (progress) =>
          setProgress(key, progress)
        )
        addUpload(imageEntryFromUpload(response.data))
      } catch (error) {
        const code = error.response?.data?.code
        toast.error(
          code === 'image_too_large'
            ? t('errors.tooLarge')
            : code === 'unsupported_image'
              ? t('errors.unsupported')
              : t('errors.uploadFailed')
        )
      } finally {
        setUploading((current) => current.filter((row) => row.key !== key))
      }
    }
  }

  const remove = (index) =>
    emit(images.filter((_, position) => position !== index))

  const move = (from, to) => {
    if (from === to || from < 0 || to < 0) return
    const next = [...images]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    emit(next)
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-gray-700">{t('title')}</h2>
        <span className="text-xs text-gray-500">
          {t('count', { count: images.length, max })}
        </span>
      </div>
      <p className="text-sm text-gray-600">{t('hint', { max })}</p>

      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={ACCEPTED_IMAGE_TYPES.join(',')}
        multiple
        className="hidden"
        disabled={disabled || atLimit}
        onChange={handleFiles}
      />
      <label
        htmlFor={inputId}
        aria-disabled={disabled || atLimit}
        className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-dashed border-gray-300 text-sm transition-colors ${
          disabled || atLimit
            ? 'text-gray-400 cursor-not-allowed'
            : 'text-primary cursor-pointer hover:border-primary hover:bg-primary/5'
        }`}
      >
        <ImagePlus className="h-4 w-4" />
        {busy ? t('uploading') : t('add')}
      </label>

      {(images.length > 0 || uploading.length > 0) && (
        <ul className="grid grid-cols-3 sm:grid-cols-4 gap-3">
          {images.map((image, index) => {
            const shared = {
              draggable: !disabled,
              onDragStart: () => setDragIndex(index),
              onDragOver: (event) => event.preventDefault(),
              onDrop: () => {
                if (dragIndex !== null) move(dragIndex, index)
                setDragIndex(null)
              },
              onDragEnd: () => setDragIndex(null),
            }
            return (
              <li
                key={image.upload_id || image.image_url || index}
                {...shared}
                aria-label={image.upload_id ? t('uploaded') : image.image_url}
                className={`relative border rounded-lg overflow-hidden group bg-gray-100 ${
                  dragIndex === index
                    ? 'border-primary opacity-60'
                    : 'border-gray-200'
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- preview of an already-loaded upload */}
                <img
                  src={image.thumb_url || image.url || image.image_url}
                  alt=""
                  className="w-full h-24 object-cover"
                  draggable={false}
                />
                {index === 0 && (
                  <span className="absolute top-1 start-1 text-xs bg-black/60 text-white px-2 py-0.5 rounded-full">
                    {t('cover')}
                  </span>
                )}
                <span className="absolute top-1 end-1 p-1 bg-white/80 rounded-full opacity-0 group-hover:opacity-100 transition-opacity cursor-grab">
                  <GripVertical className="h-3 w-3 text-gray-600" />
                </span>
                <div className="absolute bottom-1 inset-x-1 flex justify-between gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                  <button
                    type="button"
                    onClick={() => move(index, 0)}
                    disabled={index === 0 || disabled}
                    aria-label={t('makeCover')}
                    className="p-1 bg-white/90 rounded-full disabled:opacity-40"
                  >
                    <Star className="h-3 w-3 text-amber-500" />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(index)}
                    disabled={disabled}
                    aria-label={t('remove')}
                    className="p-1 bg-white/90 rounded-full disabled:opacity-40"
                  >
                    <Trash2 className="h-3 w-3 text-red-600" />
                  </button>
                </div>
              </li>
            )
          })}
          {uploading.map((row) => (
            <li
              key={row.key}
              className="relative border border-gray-200 rounded-lg overflow-hidden bg-gray-50 flex flex-col items-center justify-center h-24 gap-1"
            >
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              <span className="text-xs text-gray-500 tabular-nums">
                {row.progress}%
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
