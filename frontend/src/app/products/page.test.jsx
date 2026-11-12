/**
 * Catalogue cursor pagination — Phase 15 fixed the "only page 1 renders"
 * bug and the `in_stock: true` default that hid every classified.
 */

import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithIntl } from '../../test/i18n'
import { fetchCategoryTree } from '../../lib/catalog'
import { fetchWilayas } from '../../lib/geography'
import ProductsPage from './page'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    list: vi.fn(),
    page: vi.fn(),
    toastError: vi.fn(),
  },
}))

vi.mock('../../lib/api', () => ({
  productsAPI: {
    list: mocks.list,
    page: mocks.page,
  },
}))

vi.mock('../../lib/catalog', () => ({
  fetchCategoryTree: vi.fn().mockResolvedValue([]),
  categoryBySlug: () => null,
  effectiveDefinitions: () => [],
}))

vi.mock('../../lib/geography', () => ({
  fetchWilayas: vi.fn().mockResolvedValue([]),
}))

vi.mock('react-hot-toast', () => ({
  default: Object.assign(vi.fn(), { error: mocks.toastError }),
}))

const PHONE = {
  id: 1,
  name: 'Catalogue Phone',
  canonical_path: '/l/catalogue-phone-1',
  primary_image: null,
  base_price: '30000.00',
  category: { id: 1, slug: 'phones', name: 'Phones' },
  store_name: 'Smoke Store',
  is_available: true,
}

const ACCESSORY = {
  ...PHONE,
  id: 2,
  name: 'Catalogue Case',
  canonical_path: '/l/catalogue-case-2',
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(fetchCategoryTree).mockResolvedValue([])
  vi.mocked(fetchWilayas).mockResolvedValue([])
  mocks.list.mockResolvedValue({
    data: {
      results: [PHONE],
      next: 'http://api.test/products/?cursor=abc',
    },
  })
  mocks.page.mockResolvedValue({
    data: { results: [ACCESSORY], next: null },
  })
})

describe('products catalogue pagination', () => {
  it('does not force in_stock and appends the cursor page', async () => {
    renderWithIntl(<ProductsPage />)
    await screen.findByText('Catalogue Phone')

    const initialParams = mocks.list.mock.calls[0][0]
    expect(initialParams.in_stock).toBeUndefined()

    fireEvent.click(screen.getByRole('button', { name: 'Load more' }))

    expect(await screen.findByText('Catalogue Case')).toBeInTheDocument()
    expect(screen.getByText('Catalogue Phone')).toBeInTheDocument()
    expect(mocks.page).toHaveBeenCalledWith(
      'http://api.test/products/?cursor=abc'
    )
  })

  it('sends in_stock=true only when the user opts in', async () => {
    renderWithIntl(<ProductsPage />)
    await screen.findByText('Catalogue Phone')

    fireEvent.click(screen.getByRole('button', { name: 'Filters' }))
    fireEvent.click(screen.getByRole('checkbox', { name: /In Stock/i }))

    await waitFor(() => {
      const lastParams = mocks.list.mock.calls.at(-1)[0]
      expect(lastParams.in_stock).toBe('true')
    })
  })
})
