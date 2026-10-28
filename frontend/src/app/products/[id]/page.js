'use client'

import { useParams } from 'next/navigation'
import ProductDetail from '../../../components/product/ProductDetail'

/**
 * The legacy entry point (Phase 6). Phase 13 extracted the page into
 * `<ProductDetail>`, which redirects to the canonical `/l/<slug>-<id>` once
 * the row is loaded — this route stays so old links keep working.
 */
export default function ProductDetailPage() {
  const params = useParams()
  return <ProductDetail productId={params.id} />
}
