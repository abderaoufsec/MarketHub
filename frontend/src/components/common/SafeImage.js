'use client'

import Image from 'next/image'

import { canOptimizeImage, isRemoteImage } from '../../lib/media'

/**
 * The one image element the catalogue uses.
 *
 * * Our uploads (the API origin or a configured CDN) go through
 *   `next/image`: resized by the optimiser, lazy by default, and blur-up via
 *   the LQIP the pipeline stored.
 * * External/legacy URLs — which the API still accepts — fall back to a
 *   plain `<img>`. They must render (they are someone's photo), but they may
 *   not become a hole in the image optimiser's allow-list.
 * * Local static paths (the placeholder) stay plain: they are already small.
 */
export default function SafeImage({
  src,
  alt = '',
  className = '',
  fill = false,
  width,
  height,
  sizes,
  priority = false,
  blurDataURL,
  onLoad,
  onError,
  loading,
  ...rest
}) {
  if (!src) return null

  if (!isRemoteImage(src) || !canOptimizeImage(src)) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- not an optimisable host
      <img
        src={src}
        alt={alt}
        className={className}
        loading={loading || (priority ? 'eager' : 'lazy')}
        onLoad={onLoad}
        onError={onError}
        {...rest}
      />
    )
  }

  return (
    <Image
      src={src}
      alt={alt}
      className={className}
      fill={fill}
      width={fill ? undefined : width}
      height={fill ? undefined : height}
      sizes={sizes}
      priority={priority}
      placeholder={blurDataURL ? 'blur' : 'empty'}
      blurDataURL={blurDataURL || undefined}
      onLoad={onLoad}
      onError={onError}
      {...rest}
    />
  )
}
