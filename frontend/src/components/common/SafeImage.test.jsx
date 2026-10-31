import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import SafeImage from './SafeImage'

/**
 * Phase 14: the image element that decides between the optimiser and a plain
 * `<img>`. The rule is a security boundary as much as a performance one —
 * `next.config.js` only allows the API origin and configured CDNs, so routing
 * an arbitrary host through `next/image` would 400 at runtime.
 */
vi.mock('next/image', () => ({
  default: ({ src, alt, fill, blurDataURL, sizes }) => (
    <img
      data-testid="optimised"
      src={`/_next/image?url=${encodeURIComponent(src)}`}
      alt={alt}
      data-fill={fill ? 'true' : 'false'}
      data-blur={blurDataURL ? 'true' : 'false'}
      data-sizes={sizes}
    />
  ),
}))

describe('SafeImage', () => {
  it('optimises our own media and forwards the LQIP', () => {
    render(
      <SafeImage
        src="https://cdn.test/media/listings/a/card.webp"
        alt="photo"
        fill
        sizes="25vw"
        blurDataURL="data:image/webp;base64,abc"
      />
    )

    const image = screen.getByTestId('optimised')
    expect(image).toHaveAttribute('data-fill', 'true')
    expect(image).toHaveAttribute('data-blur', 'true')
    expect(image).toHaveAttribute('data-sizes', '25vw')
  })

  it('leaves an arbitrary external host to a plain <img>', () => {
    render(<SafeImage src="https://someone-elses-host.example/a.jpg" alt="x" />)

    expect(screen.queryByTestId('optimised')).not.toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      'https://someone-elses-host.example/a.jpg'
    )
  })

  it('keeps local static assets (the placeholder) off the optimiser', () => {
    const { container } = render(
      <SafeImage src="/placeholder-product.jpg" alt="" />
    )

    expect(screen.queryByTestId('optimised')).not.toBeInTheDocument()
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/placeholder-product.jpg'
    )
  })

  it('renders nothing at all without a source', () => {
    const { container } = render(<SafeImage src="" alt="empty" />)

    expect(container).toBeEmptyDOMElement()
  })
})
