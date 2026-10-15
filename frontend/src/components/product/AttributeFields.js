'use client'

import { useTranslations } from 'next-intl'

/**
 * Dynamic attribute form fields — Phase 12 of docs/todo.md.
 *
 * Renders one input per attribute definition, by *type*: text → text,
 * number → number, year → number (1900–2100), boolean → checkbox, enum →
 * select of the server's choices, range → a min/max pair. Labels, units,
 * required flags and choices all come from the server (`label` follows the
 * request's Accept-Language), so adding a category or a field in the admin
 * changes this form with **no deploy and no frontend change** — that is the
 * whole point of the phase.
 *
 * Controlled: the parent owns `values` (the `attributes_json` object) and
 * receives `onChange(key, value)` per edit. `errors` maps a definition key
 * to the messages the API returned under `details.attributes_json`, so a
 * rejected submit highlights the offending input by key.
 */
export default function AttributeFields({
  definitions = [],
  values = {},
  errors = {},
  onChange,
  disabled = false,
}) {
  const t = useTranslations('catalog')

  if (definitions.length === 0) return null

  const handleValue = (key, raw, type) => {
    if (type === 'boolean') {
      onChange(key, raw)
      return
    }
    onChange(key, raw === '' ? null : raw)
  }

  const renderField = (definition) => {
    const { key, label, type, required, unit, choices = [], id } = definition
    const fieldId = `attr-${key}`
    const value = values[key]
    const fieldErrors = errors[key]

    const labelNode = (
      <label
        htmlFor={fieldId}
        className="block text-sm font-medium text-gray-700 mb-2"
      >
        {label}
        {unit ? <span className="text-gray-400"> ({unit})</span> : null}
        {required && <span className="text-red-500"> *</span>}
      </label>
    )

    let input
    if (type === 'boolean') {
      return (
        <div key={id ?? key}>
          <label htmlFor={fieldId} className="flex items-center gap-2">
            <input
              type="checkbox"
              id={fieldId}
              checked={value === true}
              disabled={disabled}
              onChange={(event) => handleValue(key, event.target.checked, type)}
              className="h-4 w-4 text-primary focus:ring-primary border-gray-300 rounded"
            />
            <span className="text-sm text-gray-700">
              {label}
              {required && <span className="text-red-500"> *</span>}
            </span>
          </label>
          <FieldErrors messages={fieldErrors} />
        </div>
      )
    }

    if (type === 'enum') {
      input = (
        <select
          id={fieldId}
          value={value ?? ''}
          disabled={disabled}
          onChange={(event) => handleValue(key, event.target.value, type)}
          className="input-field"
        >
          <option value="">{t('selectValue')}</option>
          {choices.map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </select>
      )
    } else if (type === 'range') {
      const range = value && typeof value === 'object' ? value : {}
      const commitRange = (next) => {
        // Both blank = optional field left out: store nothing rather than a
        // {min: null} pair the validator would reject as "Must be a number".
        const blank = next.min == null && next.max == null
        onChange(key, blank ? null : next)
      }
      return (
        <div key={id ?? key}>
          {labelNode}
          <div className="grid grid-cols-2 gap-3">
            <input
              id={`${fieldId}-min`}
              type="number"
              placeholder={t('rangeMin')}
              value={range.min ?? ''}
              disabled={disabled}
              onChange={(event) =>
                commitRange({
                  ...range,
                  min:
                    event.target.value === ''
                      ? null
                      : Number(event.target.value),
                })
              }
              className="input-field"
            />
            <input
              id={`${fieldId}-max`}
              type="number"
              placeholder={t('rangeMax')}
              value={range.max ?? ''}
              disabled={disabled}
              onChange={(event) =>
                commitRange({
                  ...range,
                  max:
                    event.target.value === ''
                      ? null
                      : Number(event.target.value),
                })
              }
              className="input-field"
            />
          </div>
          <FieldErrors messages={fieldErrors} />
        </div>
      )
    } else {
      const inputType = type === 'number' || type === 'year' ? 'number' : 'text'
      input = (
        <input
          id={fieldId}
          type={inputType}
          {...(type === 'year'
            ? { min: 1900, max: 2100, placeholder: '2020' }
            : {})}
          value={value ?? ''}
          disabled={disabled}
          onChange={(event) => handleValue(key, event.target.value, type)}
          className="input-field"
        />
      )
    }

    return (
      <div key={id ?? key}>
        {labelNode}
        {input}
        <FieldErrors messages={fieldErrors} />
      </div>
    )
  }

  return <div className="space-y-4">{definitions.map(renderField)}</div>
}

function FieldErrors({ messages }) {
  if (!messages?.length) return null
  return (
    <p className="text-sm text-red-600 mt-1" role="alert">
      {messages[0]}
    </p>
  )
}
