/**
 * The canonical listing URL (Phase 13 of docs/todo.md): `/l/<slug>-<id>`.
 *
 * The page is a thin shell around <ProductDetail>: it parses the id out of
 * the segment and renders the same detail view the legacy /products/<id>
 * uses. A segment with no id-shaped tail is a 404 *without touching the
 * API* — there is nothing to fetch.
 */
import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithIntl } from '../../../test/i18n'
import ListingPage from './page'

const { mocks } = vi.hoisted(() => ({
  mocks: { slugId: 'velo-de-ville-123' },
}))

vi.mock('next/navigation', () => ({
  useParams: () => ({ slugId: mocks.slugId }),
}))

// The detail view is covered on its own; here it is a probe that reports
// which id the route handed it.
vi.mock('../../../components/product/ProductDetail', () => ({
  default: ({ productId }) => <div data-testid="detail">{productId}</div>,
}))

beforeEach(() => {
  mocks.slugId = 'velo-de-ville-123'
})

describe('/l/[slugId]', () => {
  it('renders the detail view with the id parsed from the slug', () => {
    renderWithIntl(<ListingPage />)

    expect(screen.getByTestId('detail')).toHaveTextContent('123')
  })

  it('keeps digit-heavy titles pointing at the trailing id', () => {
    mocks.slugId = 'iphone-15-77'
    renderWithIntl(<ListingPage />)

    expect(screen.getByTestId('detail')).toHaveTextContent('77')
  })

  it('answers a slug with no id tail as not found, without fetching', () => {
    mocks.slugId = 'just-a-slug'
    renderWithIntl(<ListingPage />)

    expect(screen.queryByTestId('detail')).not.toBeInTheDocument()
    expect(screen.getByText('Product not found')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Back to Products' })
    ).toHaveAttribute('href', '/products')
  })
})
