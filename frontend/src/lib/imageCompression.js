/**
 * Phase 14: compress a photo in the browser before it leaves the phone.
 *
 * A 12 MP camera JPEG is 3–5 MB; a listing card is 640px wide. Uploading the
 * original on a 3G connection costs the seller a minute per photo and gives
 * nobody a better picture — so the browser downscales to 1600px and re-encodes
 * to WebP before the request. The server still validates and re-encodes
 * everything it receives (a hostile client can skip this file entirely).
 *
 * Every failure path returns the original file: compression is an
 * optimisation, and an old browser without canvas must still be able to post
 * an ad.
 */

export const COMPRESS_MAX_DIMENSION = 1600
export const COMPRESS_QUALITY = 0.82
//: Below this the round-trip is not worth it (most screenshots).
export const COMPRESS_MIN_BYTES = 350 * 1024
//: Formats the server accepts; keep the two lists in step.
export const ACCEPTED_IMAGE_TYPES = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/gif',
]

export function isSupportedImage(file) {
  return Boolean(file) && ACCEPTED_IMAGE_TYPES.includes(file.type)
}

/** The scaled size for a `maxDimension` box, never enlarging. */
export function scaledDimensions(width, height, maxDimension) {
  if (!width || !height || !maxDimension) return { width, height }
  const scale = Math.min(1, maxDimension / Math.max(width, height))
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  }
}

function canvasToBlob(canvas, type, quality) {
  return new Promise((resolve) => {
    if (typeof canvas.toBlob !== 'function') {
      resolve(null)
      return
    }
    canvas.toBlob(resolve, type, quality)
  })
}

export async function compressImage(
  file,
  { maxDimension = COMPRESS_MAX_DIMENSION, quality = COMPRESS_QUALITY } = {}
) {
  if (!file) throw new Error('No file given.')
  if (!isSupportedImage(file)) throw new Error('Unsupported image type.')

  // An animated GIF would be flattened to one frame by canvas: send it as is.
  if (file.type === 'image/gif') return file
  if (file.size <= COMPRESS_MIN_BYTES) return file
  if (
    typeof document === 'undefined' ||
    typeof createImageBitmap !== 'function'
  ) {
    return file
  }

  let bitmap
  try {
    bitmap = await createImageBitmap(file)
  } catch {
    return file
  }

  try {
    const { width, height } = scaledDimensions(
      bitmap.width,
      bitmap.height,
      maxDimension
    )
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')
    if (!context) return file

    context.drawImage(bitmap, 0, 0, width, height)
    const blob = await canvasToBlob(canvas, 'image/webp', quality)
    // Only take the result when it actually helped.
    if (!blob || blob.size >= file.size) return file
    if (typeof File === 'undefined') return blob
    return new File([blob], file.name, {
      type: blob.type || 'image/webp',
      lastModified: Date.now(),
    })
  } finally {
    if (typeof bitmap.close === 'function') bitmap.close()
  }
}
