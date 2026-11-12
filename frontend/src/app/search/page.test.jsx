/**
 * `/search` — Phase 15 acceptance:
 *
 * 1. the page is a real consumer of the advanced endpoint (facets + meta);
 * 2. zero-result recovery is actionable (did-you-mean + removable filters);
 * 3. cursor `next` appends instead of replacing page 1;
 * 4. saving stores the *same canonical params* the search used.
 */

import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithIntl } from '../../test/i18n'
import { fetchCategoryTree } from '../../lib/catalog'
import { fetchWilayas } from '../../lib/geography'
import SearchPage from './page'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    search: vi.fn(),
    page: vi.fn(),
    suggestions: vi.fn(),
    recent: vi.fn(),
    saveSearch: vi.fn(),
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
    auth: { isAuthenticated: false, user: null },
  },
}))

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(''),
}))

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => mocks.auth,
}))

vi.mock('../../lib/api', () => ({
  searchAPI: {
    search: mocks.search,
    page: mocks.page,
    suggestions: mocks.suggestions,
    recent: mocks.recent,
    saveSearch: mocks.saveSearch,
  },
}))

vi.mock('react-hot-toast', () => ({
  default: { success: mocks.toastSuccess, error: mocks.toastError },
}))

vi.mock('../../lib/catalog', () => ({
  fetchCategoryTree: vi.fn().mockResolvedValue([]),
  flatCategories: () => [{ id: 1, slug: 'phones', name: 'Phones', depth: 0 }],
}))

vi.mock('../../lib/geography', () => ({
  fetchWilayas: vi.fn().mockResolvedValue([{ id: 16, name: 'Alger' }]),
}))

const PHONE = {
  id: 1,
  name: 'Samsung Galaxy S24',
  canonical_path: '/l/samsung-galaxy-s24-1',
  primary_image: null,
  base_price: '55000.00',
  category: { id: 1, slug: 'phones', name: 'Phones' },
  store_name: 'Smoke Store',
  is_available: true,
}

const CASE = {
  id: 2,
  name: 'Galaxy Case',
  canonical_path: '/l/galaxy-case-2',
  primary_image: null,
  base_price: '1500.00',
  category: { id: 1, slug: 'phones', name: 'Phones' },
  store_name: 'Smoke Store',
  is_available: true,
}

function page(results, overrides = {}) {
  return {
    data: {
      next: null,
      previous: null,
      results,
      facets: {
        category: [{ value: 'phones', label: 'Phones', count: results.length }],
        wilaya: [],
        price: [
          { value: 'under_5k', count: 1 },
          { value: '5k_20k', count: 0 },
          { value: '20k_100k', count: 0 },
          { value: 'over_100k', count: 0 },
        ],
        condition: [{ value: 'new', label: 'New', count: 1 }],
        seller_type: [
          { value: 'store', count: 1 },
          { value: 'individual', count: 0 },
        ],
        verified: [],
        photos: [
          { value: 'true', count: 1 },
          { value: 'false', count: 1 },
        ],
        posted: [],
        attributes: {},
      },
      meta: {
        total: results.length,
        sort: 'newest',
        q: '',
        did_you_mean: '',
        relaxations: [],
        nearby_wilayas: [],
        used_fuzzy: false,
        filters: {},
      },
      ...overrides,
    },
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.auth = { isAuthenticated: false, user: null }
  vi.mocked(fetchCategoryTree).mockResolvedValue([])
  vi.mocked(fetchWilayas).mockResolvedValue([{ id: 16, name: 'Alger' }])
  mocks.search.mockResolvedValue(page([PHONE]))
  mocks.suggestions.mockResolvedValue({ data: { terms: [], products: [] } })
  mocks.recent.mockResolvedValue({ data: [] })
  mocks.saveSearch.mockResolvedValue({ data: { id: 9 } })
})

describe('search page', () => {
  it('renders results, the total and the server facets', async () => {
    renderWithIntl(<SearchPage />)

    expect(await screen.findByText('Samsung Galaxy S24')).toBeInTheDocument()
    expect(screen.getByText('1 result')).toBeInTheDocument()
    expect(screen.getByText('New (1)')).toBeInTheDocument()
    expect(mocks.search).toHaveBeenCalledWith({})
  })

  it('turns a zero-result page into one-click recovery options', async () => {
    mocks.search.mockResolvedValueOnce(
      page([], {
        facets: {
          category: [],
          wilaya: [],
          price: [],
          condition: [],
          attributes: {},
        },
        meta: {
          total: 0,
          sort: 'relevance',
          q: 'samsug',
          did_you_mean: 'samsung',
          relaxations: [{ param: 'q', value: 'samsug', count: 4 }],
          nearby_wilayas: [
            { value: '16', label: 'Alger', count: 2, distance_km: 1.2 },
          ],
          used_fuzzy: true,
          filters: { q: 'samsug' },
        },
      })
    )

    renderWithIntl(<SearchPage />)

    const correction = await screen.findByRole('button', {
      name: 'Did you mean samsung?',
    })
    expect(screen.getByText('No listings found')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Remove keywords (4)' })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Alger (2)' })
    ).toBeInTheDocument()

    fireEvent.click(correction)
    await waitFor(() =>
      expect(mocks.search).toHaveBeenLastCalledWith({ q: 'samsung' })
    )
  })

  it('appends the cursor page instead of replacing page 1', async () => {
    mocks.search.mockResolvedValueOnce(
      page([PHONE], { next: 'http://api.test/search/?cursor=abc' })
    )
    mocks.page.mockResolvedValueOnce(page([CASE]))

    renderWithIntl(<SearchPage />)
    await screen.findByText('Samsung Galaxy S24')

    fireEvent.click(screen.getByRole('button', { name: /Load more/ }))

    expect(await screen.findByText('Galaxy Case')).toBeInTheDocument()
    expect(screen.getByText('Samsung Galaxy S24')).toBeInTheDocument()
    expect(mocks.page).toHaveBeenCalledWith(
      'http://api.test/search/?cursor=abc'
    )
  })

  it('saves the canonical params the search actually used', async () => {
    mocks.auth = {
      isAuthenticated: true,
      user: { email: 'buyer@example.com', phone_number: '+213555000111' },
    }
    renderWithIntl(<SearchPage />)

    fireEvent.click(
      await screen.findByRole('button', { name: 'Save this search' })
    )
    fireEvent.change(screen.getByLabelText('Name (optional)'), {
      target: { value: 'Phones' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save search' }))

    await waitFor(() => expect(mocks.saveSearch).toHaveBeenCalled())
    expect(mocks.saveSearch.mock.calls[0][0]).toMatchObject({
      name: 'Phones',
      params: {},
      frequency: 'DAILY',
      notify_email: true,
    })
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Search saved')
  })
})
