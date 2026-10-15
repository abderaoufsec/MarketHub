'use client'

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { fetchCategoryTree } from '../../lib/catalog'

/**
 * Category tree select (Phase 12 of docs/todo.md).
 *
 * Controlled: the parent owns `categoryId` (a number, or null) and posts it
 * as `category_id` — the API write contract since Phase 12. The tree comes
 * from `GET /catalog/categories/`, cached by locale in src/lib/catalog.js;
 * children render indented under their parent so the hierarchy reads at a
 * glance (a flat list of 23 slugs would not).
 *
 * Reusable everywhere a category is chosen: the seller product forms and the
 * products filter sidebar today, the fast posting wizard in Phase 13.
 */
export default function CategoryPicker({
  categoryId,
  onChange,
  disabled = false,
  required = false,
  id = 'category-picker',
}) {
  const t = useTranslations('catalog')
  const [nodes, setNodes] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchCategoryTree()
      .then((tree) => {
        if (!cancelled) setNodes(tree)
      })
      .catch(() => {
        if (!cancelled) setLoadError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (loadError) {
    return (
      <p className="text-sm text-red-600" role="alert">
        {t('loadError')}
      </p>
    )
  }

  // Depth-first flatten with an indent level, so the nested tree becomes one
  // list of <option>s without recursive JSX (children carry no depth server-side).
  const options = []
  const pushNodes = (list, depth) => {
    for (const node of list) {
      options.push(
        <option key={node.id} value={node.id}>
          {'\u00A0'.repeat(2 * depth) + node.name}
        </option>
      )
      if (node.children?.length) pushNodes(node.children, depth + 1)
    }
  }
  pushNodes(nodes, 0)

  return (
    <select
      id={id}
      value={categoryId ?? ''}
      onChange={(event) => onChange(Number(event.target.value) || null)}
      disabled={disabled || loading}
      required={required}
      className="input-field"
    >
      <option value="">
        {loading ? t('loadingCategories') : t('selectCategory')}
      </option>
      {options}
    </select>
  )
}
