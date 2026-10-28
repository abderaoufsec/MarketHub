/**
 * The fast-posting wizard (Phase 13 of docs/todo.md): "anyone can post in
 * under 90 seconds" with nothing lost to a dropped connection.
 *
 * What is pinned here:
 * 1. **Autosave across the steps.** The first step boundary creates the
 *    draft (POST /products/create/), every later boundary PATCHes it — a
 *    reload or a lost signal never costs the seller what they typed.
 * 2. **`incomplete_listing` sends the seller back to the step that owns the
 *    missing field**, not to a blank form.
 * 3. **`possible_duplicate` is a confirmation, not a wall**: "publish
 *    anyway" retries the same lifecycle action with `allow_duplicate: true`
 *    — the only knob that gate has.
 */
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithIntl } from '../../test/i18n'
import PostListingPage from './page'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    authed: true,
    push: vi.fn(),
    replace: vi.fn(),
    createListing: vi.fn(),
    updateListing: vi.fn(),
    lifecycle: vi.fn(),
    quota: vi.fn(),
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
  },
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
}))

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    isAuthenticated: mocks.authed,
    isSeller: false,
    loading: false,
  }),
}))

vi.mock('../../lib/api', () => ({
  // src/lib/catalog.js imports the raw client as the default export; the
  // wizard itself only touches productsAPI.
  default: { get: vi.fn() },
  productsAPI: {
    createListing: mocks.createListing,
    updateListing: mocks.updateListing,
    lifecycle: mocks.lifecycle,
    quota: mocks.quota,
  },
}))

vi.mock('react-hot-toast', () => ({
  default: { success: mocks.toastSuccess, error: mocks.toastError },
}))

// The pickers talk to their own endpoints; the wizard only consumes the ids
// they hand back through onChange.
vi.mock('../../components/common/CategoryPicker', () => ({
  default: ({ onChange }) => (
    <button type="button" onClick={() => onChange(7)}>
      pick-category
    </button>
  ),
}))
vi.mock('../../components/common/LocationPicker', () => ({
  default: ({ onChange }) => (
    <button
      type="button"
      onClick={() => onChange({ wilayaId: 16, communeId: 1601 })}
    >
      pick-location
    </button>
  ),
}))
vi.mock('../../components/product/AttributeFields', () => ({
  default: () => null,
}))

/** The Phase 9 failure envelope the wizard branches on `code` from. */
function envelope(code, details) {
  return {
    response: {
      status: 400,
      data: { code, message: 'rejected', details, request_id: 'req-1' },
    },
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.authed = true
  mocks.quota.mockResolvedValue({
    data: { active_listings: 3, listing_quota: 10, drafts: 1, draft_limit: 20 },
  })
})

const stepText = () => document.body.textContent

/** Walk the wizard to the final "price & publish" step. */
async function walkToPublishStep() {
  mocks.createListing.mockResolvedValue({ data: { id: 55 } })
  mocks.updateListing.mockResolvedValue({ data: { id: 55 } })

  renderWithIntl(<PostListingPage />)

  fireEvent.change(screen.getByLabelText(/^title/i), {
    target: { value: 'Vélo de ville' },
  })
  fireEvent.change(screen.getByLabelText(/^description/i), {
    target: { value: 'Bon état, cadre aluminium.' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'pick-category' }))
  fireEvent.click(screen.getByRole('button', { name: /continue/i }))
  await screen.findByText(/paste a photo url/i)

  // photos → details → location → price (autosave PATCH at each boundary)
  fireEvent.click(screen.getByRole('button', { name: /continue/i }))
  await screen.findByText(/how should buyers reach you/i)
  fireEvent.click(screen.getByRole('button', { name: /continue/i }))
  await screen.findByText(/buyers filter by wilaya/i)
  fireEvent.click(screen.getByRole('button', { name: 'pick-location' }))
  fireEvent.click(screen.getByRole('button', { name: /continue/i }))
  await screen.findByLabelText(/^price/i)
}

describe('posting wizard', () => {
  it('sends anonymous visitors to /login', () => {
    mocks.authed = false

    renderWithIntl(<PostListingPage />)

    expect(mocks.replace).toHaveBeenCalledWith('/login?next=/post')
    expect(mocks.createListing).not.toHaveBeenCalled()
  })

  it('shows the quota the seller is about to spend', async () => {
    renderWithIntl(<PostListingPage />)

    await waitFor(() => expect(stepText()).toContain('3 of 10 active listings'))
    expect(stepText()).toContain('1 of 20 drafts')
  })

  it('creates the draft on the first step boundary and PATCHes after', async () => {
    await walkToPublishStep()

    // One POST with everything typed so far…
    expect(mocks.createListing).toHaveBeenCalledTimes(1)
    expect(mocks.createListing).toHaveBeenCalledWith({
      listing_type: 'FOR_SALE',
      name: 'Vélo de ville',
      description: 'Bon état, cadre aluminium.',
      attributes_json: {},
      contact_mode: 'PHONE',
      price_mode: 'FIXED',
      category_id: 7,
    })
    // …then PATCHes against that draft id at every later boundary.
    expect(mocks.updateListing).toHaveBeenCalled()
    for (const [id] of mocks.updateListing.mock.calls) {
      expect(id).toBe(55)
    }
  })

  it('publishes through the lifecycle and lands on the canonical URL', async () => {
    mocks.lifecycle.mockResolvedValue({
      data: { id: 55, status: 'ACTIVE', canonical_path: '/l/velo-de-ville-55' },
    })
    await walkToPublishStep()

    fireEvent.click(screen.getByRole('button', { name: /^publish$/i }))

    await waitFor(() =>
      expect(mocks.lifecycle).toHaveBeenCalledWith(55, 'publish', {})
    )
    await waitFor(() =>
      expect(mocks.push).toHaveBeenCalledWith('/l/velo-de-ville-55')
    )
    expect(mocks.toastSuccess).toHaveBeenCalled()
  })

  it('jumps back to the step that owns a missing required field', async () => {
    mocks.lifecycle.mockRejectedValue(
      envelope('incomplete_listing', { missing: ['wilaya'] })
    )
    await walkToPublishStep()

    fireEvent.click(screen.getByRole('button', { name: /^publish$/i }))

    // The seller lands on the location step, told what is missing.
    await screen.findByText(/buyers filter by wilaya/i)
    expect(mocks.toastError).toHaveBeenCalledWith(
      expect.stringContaining('wilaya')
    )
    expect(mocks.push).not.toHaveBeenCalled()
  })

  it('offers "publish anyway" on a duplicate and retries with the flag', async () => {
    mocks.lifecycle
      .mockRejectedValueOnce(
        envelope('possible_duplicate', {
          duplicate_of: 9,
          duplicate_name: 'Vélo de ville',
        })
      )
      .mockResolvedValueOnce({
        data: {
          id: 55,
          status: 'ACTIVE',
          canonical_path: '/l/velo-de-ville-55',
        },
      })
    await walkToPublishStep()

    fireEvent.click(screen.getByRole('button', { name: /^publish$/i }))

    // The warning names the ad it looks like, in place — not a dead end.
    await screen.findByText(/looks a lot like your ad/i)
    expect(screen.getByText(/Vélo de ville/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /publish anyway/i }))

    await waitFor(() => expect(mocks.lifecycle).toHaveBeenCalledTimes(2))
    expect(mocks.lifecycle).toHaveBeenNthCalledWith(1, 55, 'publish', {})
    // The confirm is the *only* thing allow_duplicate unlocks.
    expect(mocks.lifecycle).toHaveBeenNthCalledWith(2, 55, 'publish', {
      allow_duplicate: true,
    })
    await waitFor(() =>
      expect(mocks.push).toHaveBeenCalledWith('/l/velo-de-ville-55')
    )
  })

  it('refuses to advance past step 1 without title and category', async () => {
    mocks.createListing.mockResolvedValue({ data: { id: 55 } })
    renderWithIntl(<PostListingPage />)
    // let the quota banner effect settle before driving the form
    await screen.findByText(/3 of 10 active listings/)

    fireEvent.click(screen.getByRole('button', { name: /continue/i }))

    expect(mocks.toastError).toHaveBeenCalledWith(
      expect.stringContaining('title')
    )
    expect(mocks.createListing).not.toHaveBeenCalled()
  })

  it('lands on drafts (never the catalogue) after a failed publish', async () => {
    mocks.lifecycle.mockRejectedValue(
      envelope('quota_reached', { quota: 10, active: 10 })
    )
    await walkToPublishStep()

    fireEvent.click(screen.getByRole('button', { name: /^publish$/i }))

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalled())
    expect(mocks.push).not.toHaveBeenCalled()
    // Still on the wizard, draft intact.
    expect(screen.getByRole('button', { name: /^publish$/i })).toBeEnabled()
  })
})
