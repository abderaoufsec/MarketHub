'use client'

import { useParams } from 'next/navigation'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import ProductDetail from '../../../components/product/ProductDetail'
import { parseListingId } from '../../../lib/listing'

/**
 * The canonical listing URL (Phase 13): `/l/<slug>-<id>`.
 *
 * The id is parsed from the trailing `-<digits>` — the slug is the API's,
 * pure SEO sugar, so a renamed ad changes the slug and keeps the id. A stale
 * slug or the legacy `/products/<id>` both land here and are normalized to
 * `canonical_path` by `<ProductDetail>`; an id-shaped URL that parses to
 * nothing is simply not a listing.
 */
export default function ListingPage() {
  const t = useTranslations('products')
  const params = useParams()
  const id = parseListingId(params.slugId)

  if (!id) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8 text-center">
        <p className="text-gray-500 text-lg">{t('notFound')}</p>
        <Link
          href="/products"
          className="text-primary hover:text-secondary mt-4 inline-block"
        >
          {t('backToProducts')}
        </Link>
      </div>
    )
  }

  return <ProductDetail productId={id} />
}
