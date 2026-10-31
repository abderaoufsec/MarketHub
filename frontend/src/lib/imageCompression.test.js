import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ACCEPTED_IMAGE_TYPES,
  COMPRESS_MIN_BYTES,
  compressImage,
  isSupportedImage,
  scaledDimensions,
} from './imageCompression'

/**
 * Phase 14: the browser half of the media pipeline.
 *
 * The contract that matters on a 3G phone is "the upload is smaller than the
 * photo", and the contract that matters everywhere is "a browser that cannot
 * compress must still be able to post": every failure path returns the
 * original File untouched.
 */

function makeFile({
  size = 2 * COMPRESS_MIN_BYTES,
  type = 'image/jpeg',
  name = 'photo.jpg',
} = {}) {
  return new File([new Uint8Array(size)], name, { type })
}

afterEach(() => {
  vi.restoreAllMocks()
  delete globalThis.createImageBitmap
})

describe('scaledDimensions', () => {
  it('downscales the long edge to the box', () => {
    expect(scaledDimensions(4000, 3000, 1600)).toEqual({
      width: 1600,
      height: 1200,
    })
    expect(scaledDimensions(3000, 4000, 1600)).toEqual({
      width: 1200,
      height: 1600,
    })
  })

  it('never enlarges a small photo', () => {
    expect(scaledDimensions(640, 480, 1600)).toEqual({
      width: 640,
      height: 480,
    })
  })
})

describe('isSupportedImage', () => {
  it('accepts exactly the formats the server accepts', () => {
    for (const type of ACCEPTED_IMAGE_TYPES) {
      expect(isSupportedImage(makeFile({ type }))).toBe(true)
    }
    expect(isSupportedImage(makeFile({ type: 'image/heic' }))).toBe(false)
    expect(isSupportedImage(null)).toBe(false)
  })
})

describe('compressImage', () => {
  it('rejects a file that is not an image at all', async () => {
    const pdf = new File(['%PDF'], 'doc.pdf', { type: 'application/pdf' })

    await expect(compressImage(pdf)).rejects.toThrow(/unsupported/i)
  })

  it('sends an animated GIF untouched (canvas would keep one frame)', async () => {
    const gif = makeFile({ type: 'image/gif', name: 'anim.gif' })

    await expect(compressImage(gif)).resolves.toBe(gif)
  })

  it('skips files that are already small', async () => {
    const small = makeFile({ size: 10 * 1024 })

    await expect(compressImage(small)).resolves.toBe(small)
  })

  it('falls back to the original when the browser cannot decode', async () => {
    globalThis.createImageBitmap = vi.fn().mockRejectedValue(new Error('nope'))
    const file = makeFile()

    await expect(compressImage(file)).resolves.toBe(file)
  })

  it('re-encodes a large photo down to the box, as WebP', async () => {
    const bitmap = { width: 4000, height: 3000, close: vi.fn() }
    globalThis.createImageBitmap = vi.fn().mockResolvedValue(bitmap)

    const context = { drawImage: vi.fn() }
    const canvas = {
      width: 0,
      height: 0,
      getContext: vi.fn(() => context),
      toBlob: vi.fn((resolve) =>
        resolve(new Blob(['tiny'], { type: 'image/webp' }))
      ),
    }
    const createElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag) =>
      tag === 'canvas' ? canvas : createElement(tag)
    )

    const file = makeFile()
    const result = await compressImage(file)

    expect(result).not.toBe(file)
    expect(result.name).toBe('photo.jpg')
    expect(result.type).toBe('image/webp')
    expect(result.size).toBeLessThan(file.size)
    expect(canvas.width).toBe(1600)
    expect(canvas.height).toBe(1200)
    expect(bitmap.close).toHaveBeenCalled()
  })

  it('keeps the original when re-encoding makes the file bigger', async () => {
    globalThis.createImageBitmap = vi.fn().mockResolvedValue({
      width: 4000,
      height: 3000,
      close: vi.fn(),
    })
    const canvas = {
      getContext: () => ({ drawImage: vi.fn() }),
      toBlob: (resolve) =>
        resolve(
          new Blob([new Uint8Array(5 * COMPRESS_MIN_BYTES)], {
            type: 'image/webp',
          })
        ),
    }
    const createElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag) =>
      tag === 'canvas' ? canvas : createElement(tag)
    )

    const file = makeFile()
    await expect(compressImage(file)).resolves.toBe(file)
  })
})
