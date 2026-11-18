import { screen } from '@testing-library/react'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { renderWithIntl } from '../../test/i18n'
import SellerBadge from './SellerBadge'

describe('SellerBadge (Phase 17)', () => {
  it('renders every verified tier from the server payload', () => {
    renderWithIntl(
      <SellerBadge
        badges={[{ code: 'PHONE' }, { code: 'ID' }, { code: 'STORE' }]}
      />
    )

    expect(screen.getByText('Phone verified')).toBeInTheDocument()
    expect(screen.getByText('ID verified')).toBeInTheDocument()
    expect(screen.getByText('Store verified')).toBeInTheDocument()
  })

  it('accepts a bare tier as a single badge', () => {
    renderWithIntl(<SellerBadge tier="ID" />)

    expect(screen.getByText('ID verified')).toBeInTheDocument()
  })

  it('hides unverified accounts unless explicitly asked', () => {
    const { rerender } = renderWithIntl(
      <SellerBadge badges={[{ code: 'UNVERIFIED' }]} />
    )
    expect(screen.queryByText('Unverified')).not.toBeInTheDocument()

    rerender(<SellerBadge badges={[{ code: 'UNVERIFIED' }]} showUnverified />)
    expect(screen.getByText('Unverified')).toBeInTheDocument()
  })

  it('renders nothing when there is no tier at all', () => {
    const { container } = renderWithIntl(<SellerBadge />)

    expect(container).toBeEmptyDOMElement()
  })

  it('localises the badge labels', () => {
    renderWithIntl(<SellerBadge badges={[{ code: 'STORE' }]} />, {
      locale: 'fr',
    })

    expect(screen.getByText('Boutique vérifiée')).toBeInTheDocument()
  })
})
