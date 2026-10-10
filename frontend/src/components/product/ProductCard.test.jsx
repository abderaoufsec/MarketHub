import { render, screen } from '@testing-library/react'
import React from 'react'
import { describe, expect, it, vi } from 'vitest'

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
  category: 'phones',
  store_name: 'TechStore Blida',
  is_available: true,
  images: [{ image_url: 'https://cdn.example.com/s24.jpg' }],
}

describe('ProductCard', () => {
  it('renders name, store, formatted price and category', () => {
    render(<ProductCard product={PRODUCT} />)

    expect(
      screen.getByRole('heading', { name: 'Galaxy S24' })
    ).toBeInTheDocument()
    expect(screen.getByText('TechStore Blida')).toBeInTheDocument()
    expect(screen.getByText('$45000.00')).toBeInTheDocument()
    expect(screen.getByText('phones')).toBeInTheDocument()
  })

  it('links to the product detail page', () => {
    render(<ProductCard product={PRODUCT} />)

    expect(screen.getByRole('link')).toHaveAttribute('href', '/products/42')
  })

  it('uses the first image when present', () => {
    render(<ProductCard product={PRODUCT} />)

    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      'https://cdn.example.com/s24.jpg'
    )
  })

  it('falls back to the store object when store_name is absent', () => {
    const { store_name, ...rest } = PRODUCT
    render(
      <ProductCard
        product={{ ...rest, store: { store_name: 'Nested Store' } }}
      />
    )

    expect(screen.getByText('Nested Store')).toBeInTheDocument()
  })

  it('shows a placeholder image path when the product has no images', () => {
    const { images, ...rest } = PRODUCT
    render(<ProductCard product={rest} />)

    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      '/placeholder-product.jpg'
    )
  })

  it('renders an out-of-stock badge for unavailable products', () => {
    render(<ProductCard product={{ ...PRODUCT, is_available: false }} />)

    expect(screen.getByText('Out of Stock')).toBeInTheDocument()
  })

  it('does not render an out-of-stock badge for available products', () => {
    render(<ProductCard product={PRODUCT} />)

    expect(screen.queryByText('Out of Stock')).not.toBeInTheDocument()
  })

  it('does not crash when base_price is missing', () => {
    // Note: the current renderer shows "$NaN" for a missing price; the
    // formatting fix belongs with the catalog work (Phase 12), so this test
    // only pins the "must not throw" contract.
    const { base_price, ...rest } = PRODUCT
    render(<ProductCard product={{ ...rest, base_price: undefined }} />)

    expect(
      screen.getByRole('heading', { name: 'Galaxy S24' })
    ).toBeInTheDocument()
  })
})
