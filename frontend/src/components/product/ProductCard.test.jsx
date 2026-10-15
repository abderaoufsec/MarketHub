import { screen } from '@testing-library/react'
import React from 'react'
import { describe, expect, it, vi } from 'vitest'

import { renderWithIntl } from '../../test/i18n'
import ProductCard from './ProductCard'

// next/link needs the App Router context; assert on the rendered anchor.
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}))

// framer-motion renders fine in jsdom, but mock it to keep assertions about
// structure rather than animation state. Components are cached per tag so each
// one gets a stable name (satisfies react/display-name). vi.mock factories are
// hoisted, so everything must live inside the factory.
vi.mock('framer-motion', async () => {
  const React = await import('react')
  const cache = new Map()
  const proxy = new Proxy(
    {},
    {
      get: (_target, tag) => {
        if (!cache.has(tag)) {
          const MotionStub = React.forwardRef((props, ref) => {
            const {
              initial,
              animate,
              exit,
              transition,
              whileHover,
              whileTap,
              ...dom
            } = props
            return React.createElement(tag, { ...dom, ref })
          })
          MotionStub.displayName = `motion.${tag}`
          cache.set(tag, MotionStub)
        }
        return cache.get(tag)
      },
    }
  )
  const AnimatePresence = ({ children }) => children
  AnimatePresence.displayName = 'AnimatePresence'
  return { motion: proxy, AnimatePresence }
})

const PRODUCT = {
  id: 42,
  name: 'Galaxy S24',
  base_price: '45000.00',
  // Phase 12: the serializer nests the catalog FK as {id, slug, name}.
  category: { id: 7, slug: 'phones', name: 'Téléphones' },
  store_name: 'TechStore Blida',
  is_available: true,
  primary_image: 'https://cdn.example.com/s24.jpg',
}

describe('ProductCard', () => {
  it('renders name, store, DZD price and category', () => {
    renderWithIntl(<ProductCard product={PRODUCT} />)

    expect(
      screen.getByRole('heading', { name: 'Galaxy S24' })
    ).toBeInTheDocument()
    expect(screen.getByText('TechStore Blida')).toBeInTheDocument()
    // DZD via usePrice — never a bare "$" amount.
    expect(screen.getByText('DZD 45,000')).toBeInTheDocument()
    // The localized name from the nested object — never "[object Object]".
    expect(screen.getByText('Téléphones')).toBeInTheDocument()
  })

  it('falls back to a legacy string category, and hides a null one', () => {
    const { rerender } = renderWithIntl(
      <ProductCard product={{ ...PRODUCT, category: 'phones' }} />
    )
    expect(screen.getByText('phones')).toBeInTheDocument()

    rerender(<ProductCard product={{ ...PRODUCT, category: null }} />)
    expect(screen.queryByText('phones')).not.toBeInTheDocument()
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument()
  })

  it('links to the product detail page', () => {
    renderWithIntl(<ProductCard product={PRODUCT} />)

    expect(screen.getByRole('link')).toHaveAttribute('href', '/products/42')
  })

  it('renders the primary image returned by the serializer', () => {
    renderWithIntl(<ProductCard product={PRODUCT} />)

    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      'https://cdn.example.com/s24.jpg'
    )
  })

  it('falls back to image_url when primary_image is absent', () => {
    renderWithIntl(
      <ProductCard
        product={{
          ...PRODUCT,
          primary_image: null,
          image_url: 'https://cdn.example.com/legacy.jpg',
        }}
      />
    )

    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      'https://cdn.example.com/legacy.jpg'
    )
  })

  it('falls back to the store object when store_name is absent', () => {
    const { store_name, ...rest } = PRODUCT
    renderWithIntl(
      <ProductCard
        product={{ ...rest, store: { store_name: 'Nested Store' } }}
      />
    )

    expect(screen.getByText('Nested Store')).toBeInTheDocument()
  })

  it('shows the placeholder when the product has no image at all', () => {
    const { primary_image, ...rest } = PRODUCT
    renderWithIntl(<ProductCard product={rest} />)

    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      '/placeholder-product.jpg'
    )
  })

  it('renders an out-of-stock badge for unavailable products', () => {
    renderWithIntl(
      <ProductCard product={{ ...PRODUCT, is_available: false }} />
    )

    expect(screen.getByText('Out of Stock')).toBeInTheDocument()
  })

  it('does not render an out-of-stock badge for available products', () => {
    renderWithIntl(<ProductCard product={PRODUCT} />)

    expect(screen.queryByText('Out of Stock')).not.toBeInTheDocument()
  })

  it('does not crash when base_price is missing', () => {
    // usePrice renders a zero amount (DZD 0) for a missing price; this test
    // pins the "must not throw" contract.
    renderWithIntl(
      <ProductCard product={{ ...PRODUCT, base_price: undefined }} />
    )

    expect(
      screen.getByRole('heading', { name: 'Galaxy S24' })
    ).toBeInTheDocument()
  })
})
