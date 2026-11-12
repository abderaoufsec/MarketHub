/**
 * Home discovery feed — Phase 15 replaced the static hero-only landing page
 * with cursor-paginated "latest" and "trending" sections plus category chips.
 */

import { fireEvent, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithIntl } from '../test/i18n'
import Home from './page'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    products: vi.fn(),
    page: vi.fn(),
    categories: vi.fn(),
  },
}))

vi.mock('../lib/api', () => ({
  feedAPI: {
    products: mocks.products,
    page: mocks.page,
    categories: mocks.categories,
  },
}))

const LATEST = {
  id: 1,
  name: 'Fresh Laptop',
  canonical_path: '/l/fresh-laptop-1',
  primary_image: null,
  base_price: '80000.00',
  category: { id: 1, slug: 'electronics', name: 'Electronics' },
  store_name: 'Smoke Store',
  is_available: true,
}

const TRENDING = {
  ...LATEST,
  id: 2,
  name: 'Trending Phone',
  canonical_path: '/l/trending-phone-2',
}

const OLDER = {
  ...LATEST,
  id: 3,
  name: 'Older Laptop',
  canonical_path: '/l/older-laptop-3',
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.products.mockImplementation(({ section }) =>
    Promise.resolve({
      data: {
        results: section === 'latest' ? [LATEST] : [TRENDING],
        next:
          section === 'latest'
            ? 'http://api.test/products/feed/?section=latest&cursor=abc'
            : null,
      },
    })
  )
  mocks.page.mockResolvedValue({
    data: { results: [OLDER], next: null },
  })
  mocks.categories.mockResolvedValue({
    data: [{ id: 1, name: 'Electronics', slug: 'electronics', count: 12 }],
  })
})

describe('home feed', () => {
  it('renders latest, trending and category shortcuts from the API', async () => {
    renderWithIntl(<Home />)

    expect(await screen.findByText('Fresh Laptop')).toBeInTheDocument()
    expect(await screen.findByText('Trending Phone')).toBeInTheDocument()
    expect(screen.getByText('Latest listings')).toBeInTheDocument()
    expect(screen.getByText('Trending now')).toBeInTheDocument()

    const categoryLink = screen
      .getAllByRole('link', { name: /Electronics/ })
      .find(
        (link) => link.getAttribute('href') === '/search?category=electronics'
      )
    expect(categoryLink).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Search all listings' })
    ).toHaveAttribute('href', '/search')
  })

  it('loads the next cursor page into the section', async () => {
    renderWithIntl(<Home />)
    await screen.findByText('Fresh Laptop')

    fireEvent.click(screen.getByRole('button', { name: 'Load more' }))

    expect(await screen.findByText('Older Laptop')).toBeInTheDocument()
    expect(screen.getByText('Fresh Laptop')).toBeInTheDocument()
    expect(mocks.page).toHaveBeenCalledWith(
      'http://api.test/products/feed/?section=latest&cursor=abc'
    )
  })
})
