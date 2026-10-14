'use client'

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { fetchCommunes, fetchWilayas } from '../../lib/geography'

/**
 * Wilaya → commune select (Phase 11 of docs/todo.md).
 *
 * Controlled: the parent owns `{ wilayaId, communeId }` and receives a single
 * `onChange` for both — picking a different wilaya always clears the commune,
 * because a commune id only means something inside its wilaya. Commune is
 * optional (the API accepts a wilaya-only address; many rural deliveries only
 * need one), wilaya is not.
 *
 * Reusable everywhere location is collected: checkout's address form today,
 * listing forms and filters from Phases 13/15.
 */
export default function LocationPicker({
  wilayaId,
  communeId,
  onChange,
  disabled = false,
  required = false,
}) {
  const t = useTranslations('geography')
  const [wilayas, setWilayas] = useState([])
  const [communes, setCommunes] = useState([])
  const [wilayasLoading, setWilayasLoading] = useState(true)
  const [communesLoading, setCommunesLoading] = useState(false)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchWilayas()
      .then((data) => {
        if (!cancelled) setWilayas(data)
      })
      .catch(() => {
        if (!cancelled) setLoadError(true)
      })
      .finally(() => {
        if (!cancelled) setWilayasLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    if (!wilayaId) {
      setCommunes([])
      return undefined
    }
    setCommunesLoading(true)
    fetchCommunes(wilayaId)
      .then((data) => {
        if (!cancelled) setCommunes(data)
      })
      .catch(() => {
        if (!cancelled) setCommunes([])
      })
      .finally(() => {
        if (!cancelled) setCommunesLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [wilayaId])

  const handleWilayaChange = (event) => {
    const nextWilayaId = Number(event.target.value) || null
    // A commune from the old wilaya would be rejected by the API — clear it.
    onChange({ wilayaId: nextWilayaId, communeId: null })
  }

  const handleCommuneChange = (event) => {
    onChange({ wilayaId, communeId: Number(event.target.value) || null })
  }

  if (loadError) {
    return (
      <p className="text-sm text-red-600" role="alert">
        {t('loadError')}
      </p>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div>
        <label
          htmlFor="location-wilaya"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          {t('wilaya')}
          {required && <span className="text-red-500"> *</span>}
        </label>
        <select
          id="location-wilaya"
          value={wilayaId ?? ''}
          onChange={handleWilayaChange}
          disabled={disabled || wilayasLoading}
          required={required}
          className="input-field"
        >
          <option value="">
            {wilayasLoading ? t('loadingWilayas') : t('selectWilaya')}
          </option>
          {wilayas.map((wilaya) => (
            <option key={wilaya.id} value={wilaya.id}>
              {wilaya.name}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label
          htmlFor="location-commune"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          {t('commune')}
        </label>
        <select
          id="location-commune"
          value={communeId ?? ''}
          onChange={handleCommuneChange}
          disabled={disabled || !wilayaId || communesLoading}
          className="input-field"
        >
          <option value="">
            {!wilayaId
              ? t('communeNeedsWilaya')
              : communesLoading
                ? t('loadingCommunes')
                : t('selectCommune')}
          </option>
          {communes.map((commune) => (
            <option key={commune.id} value={commune.id}>
              {commune.name}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
