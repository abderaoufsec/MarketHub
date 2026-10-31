import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithIntl } from '../../test/i18n'
import ImageUploader, {
  imageEntryFromUpload,
  imageEntryPayload,
} from './ImageUploader'

/**
 * Phase 14: the photo grid shared by the posting wizard and the seller forms.
 *
 * Pinned here: an upload becomes a form entry, the list order *is* the cover,
 * and the two write shapes (an upload id, a legacy URL) are the only things
 * that ever leave the component.
 */
const { mocks } = vi.hoisted(() => ({
  mocks: { upload: vi.fn(), toastError: vi.fn() },
}))

vi.mock('../../lib/api', () => ({
  mediaAPI: { upload: mocks.upload },
}))

vi.mock('react-hot-toast', () => ({
  default: { error: mocks.toastError, success: vi.fn() },
}))

const PHOTO_A = {
  upload_id: 1,
  url: '/media/a/card.webp',
  thumb_url: '/media/a/thumb.webp',
  lqip: '',
}
const PHOTO_B = {
  upload_id: 2,
  url: '/media/b/card.webp',
  thumb_url: '/media/b/thumb.webp',
  lqip: '',
}

function pick(container, files) {
  const input = container.querySelector('input[type="file"]')
  fireEvent.change(input, { target: { files } })
  return input
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('image payload helpers', () => {
  it('keeps the read-only preview fields out of the write payload', () => {
    expect(imageEntryPayload(PHOTO_A)).toEqual({ upload_id: 1 })
    expect(imageEntryPayload({ image_url: 'https://x.test/a.jpg' })).toEqual({
      image_url: 'https://x.test/a.jpg',
    })
    expect(imageEntryPayload({})).toBe(null)
  })

  it('maps an upload response to a grid entry with a thumb and the LQIP', () => {
    expect(
      imageEntryFromUpload({
        id: 7,
        url: 'http://api.test/media/x/full.webp',
        card_url: 'http://api.test/media/x/card.webp',
        thumb_url: 'http://api.test/media/x/thumb.webp',
        lqip: 'data:image/webp;base64,abc',
        width: 900,
        height: 700,
      })
    ).toEqual({
      upload_id: 7,
      url: 'http://api.test/media/x/card.webp',
      thumb_url: 'http://api.test/media/x/thumb.webp',
      lqip: 'data:image/webp;base64,abc',
      width: 900,
      height: 700,
    })
  })
})

describe('ImageUploader', () => {
  it('uploads a picked photo and hands the entry to the parent', async () => {
    mocks.upload.mockResolvedValue({
      data: {
        id: 9,
        url: 'http://api.test/media/x/full.webp',
        card_url: 'http://api.test/media/x/card.webp',
        thumb_url: 'http://api.test/media/x/thumb.webp',
        lqip: 'data:image/webp;base64,abc',
        width: 800,
        height: 600,
      },
    })
    const onChange = vi.fn()
    const { container } = renderWithIntl(
      <ImageUploader images={[]} onChange={onChange} />
    )

    pick(container, [new File(['x'], 'photo.jpg', { type: 'image/jpeg' })])

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith([
        expect.objectContaining({
          upload_id: 9,
          thumb_url: expect.stringContaining('thumb.webp'),
        }),
      ])
    )
    expect(mocks.upload).toHaveBeenCalledTimes(1)
  })

  it('refuses a file that is not an image', async () => {
    const onChange = vi.fn()
    const { container } = renderWithIntl(
      <ImageUploader images={[]} onChange={onChange} />
    )

    pick(container, [
      new File(['%PDF'], 'doc.pdf', { type: 'application/pdf' }),
    ])

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalled())
    expect(mocks.upload).not.toHaveBeenCalled()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('stops at the maximum instead of silently dropping photos', async () => {
    const images = Array.from({ length: 15 }, (_, index) => ({
      upload_id: index + 1,
      thumb_url: `/media/${index}/thumb.webp`,
    }))
    const onChange = vi.fn()
    const { container } = renderWithIntl(
      <ImageUploader images={images} onChange={onChange} max={15} />
    )

    pick(container, [new File(['x'], 'extra.jpg', { type: 'image/jpeg' })])

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalled())
    expect(mocks.upload).not.toHaveBeenCalled()
  })

  it('removes a photo without touching the others', () => {
    const onChange = vi.fn()
    renderWithIntl(
      <ImageUploader images={[PHOTO_A, PHOTO_B]} onChange={onChange} />
    )

    fireEvent.click(screen.getAllByLabelText('Remove photo')[1])

    expect(onChange).toHaveBeenCalledWith([PHOTO_A])
  })

  it('makes a photo the cover by moving it first', () => {
    const onChange = vi.fn()
    renderWithIntl(
      <ImageUploader images={[PHOTO_A, PHOTO_B]} onChange={onChange} />
    )

    fireEvent.click(screen.getAllByLabelText('Make cover')[1])

    expect(onChange).toHaveBeenCalledWith([PHOTO_B, PHOTO_A])
  })

  it('reorders by dragging one tile onto another', () => {
    const onChange = vi.fn()
    renderWithIntl(
      <ImageUploader images={[PHOTO_A, PHOTO_B]} onChange={onChange} />
    )
    const tiles = screen.getAllByRole('listitem')

    fireEvent.dragStart(tiles[0])
    fireEvent.dragOver(tiles[1])
    fireEvent.drop(tiles[1])

    expect(onChange).toHaveBeenCalledWith([PHOTO_B, PHOTO_A])
  })
})
