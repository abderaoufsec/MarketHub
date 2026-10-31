'use client'

import Link from 'next/link'
import { ShoppingCart } from 'lucide-react'
import { motion } from 'framer-motion'
import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { usePrice } from '../../lib/currency'
import SafeImage from '../common/SafeImage'

export default function ProductCard({ product, index = 0 }) {
  const t = useTranslations('products')
  const price = usePrice()
  // ProductListSerializer exposes `primary_image`; `image_url` is kept only as
  // a defensive fallback for payloads that still ship the old shape, and the
  // placeholder (plus the error state below) covers "no image at all".
  const imageUrl =
    product.primary_image || product.image_url || '/placeholder-product.jpg'
  const [imageError, setImageError] = useState(false)
  const [imageLoading, setImageLoading] = useState(true)

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.1 }}
      whileHover={{ y: -8 }}
      className="h-full"
    >
      {/* Phase 13: the canonical URL is /l/<slug>-<id>; /products/<id>
          remains only for payloads that predate it. */}
      <Link href={product.canonical_path || `/products/${product.id}`}>
        <div className="bg-white rounded-lg shadow-sm overflow-hidden hover:shadow-xl transition-all duration-300 cursor-pointer h-full flex flex-col border border-gray-100 hover:border-primary/20 group">
          <div className="relative h-48 bg-gray-200 overflow-hidden">
            {imageLoading && !imageError && (
              <div className="absolute inset-0 bg-gray-200 animate-pulse" />
            )}
            {!imageError ? (
              <SafeImage
                src={imageUrl}
                alt={product.name}
                fill
                sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw"
                blurDataURL={product.primary_image_lqip}
                className={`object-cover transition-all duration-500 group-hover:scale-110 ${
                  imageLoading ? 'opacity-0' : 'opacity-100'
                }`}
                onLoad={() => setImageLoading(false)}
                onError={() => {
                  setImageError(true)
                  setImageLoading(false)
                }}
              />
            ) : (
              <div className="w-full h-full bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center">
                <ShoppingCart className="h-12 w-12 text-gray-400" />
              </div>
            )}
            {!product.is_available && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="absolute inset-0 bg-black/60 flex items-center justify-center backdrop-blur-sm"
              >
                <span className="text-white font-semibold px-4 py-2 bg-black/50 rounded-full">
                  {t('outOfStock')}
                </span>
              </motion.div>
            )}
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              whileHover={{ opacity: 1, scale: 1 }}
              className="absolute top-2 end-2 opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <div className="p-2 rounded-full bg-white/90 backdrop-blur-sm shadow-md">
                <ShoppingCart className="h-4 w-4 text-primary" />
              </div>
            </motion.div>
          </div>
          <div className="p-4 flex-grow flex flex-col">
            <h3 className="text-lg font-semibold text-gray-900 mb-1 line-clamp-2 group-hover:text-primary transition-colors">
              {product.name}
            </h3>
            <p className="text-sm text-gray-600 mb-2 line-clamp-1">
              {/* A classified has no store (store_name is null, not absent):
                  its identity on the card is the person who posted it. */}
              {product.store_name ||
                product.store?.store_name ||
                product.seller_name ||
                t('defaultStoreName')}
            </p>
            <div className="flex items-center justify-between mt-auto">
              <motion.span
                whileHover={{ scale: 1.05 }}
                className="text-xl font-bold text-primary"
              >
                {product.base_price == null
                  ? t('priceOnRequest')
                  : price(product.base_price)}
              </motion.span>
            </div>
            {/* Phase 12: `category` is the nested {id, slug, name} object —
                render the localized name, and never a bare object. */}
            {product.category && (
              <motion.span
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                className="inline-block mt-2 text-xs bg-gradient-to-r from-primary/10 to-secondary/10 text-primary font-medium px-3 py-1 rounded-full w-fit"
              >
                {product.category.name || product.category}
              </motion.span>
            )}
          </div>
        </div>
      </Link>
    </motion.div>
  )
}
