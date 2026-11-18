'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  Flag,
  Gavel,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from 'lucide-react'
import { useTranslations } from 'next-intl'
import toast from 'react-hot-toast'

import LoadingSpinner from '../../components/common/LoadingSpinner'
import { useAuth } from '../../context/AuthContext'
import { trustAPI } from '../../lib/api'
import { apiErrorMessage } from '../../lib/errors'

const TABS = ['reports', 'verifications', 'appeals']
const REPORT_ACTIONS = ['', 'listing_removed', 'user_banned', 'user_suspended']

function formatDate(value) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

/**
 * Staff moderation queue (Phase 17).
 *
 * A thin UI over `/trust/admin/*`: the overview counts, then one tab per
 * queue. Every mutation is a single POST whose reply replaces the row, so the
 * page never guesses what the server did. Non-staff callers get a 403 from the
 * API regardless of what the client renders, so the client-side `is_staff`
 * check is only a courtesy.
 */
export default function ModerationPage() {
  const t = useTranslations('trust.moderation')
  const { user, isAuthenticated, loading: authLoading } = useAuth()
  const [tab, setTab] = useState('reports')
  const [overview, setOverview] = useState(null)
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)

  const loadOverview = useCallback(() => {
    trustAPI.admin
      .overview()
      .then((response) => setOverview(response.data))
      .catch(() => {})
  }, [])

  const loadRows = useCallback(
    (which) => {
      setLoading(true)
      const request =
        which === 'reports'
          ? trustAPI.admin.reports({ status: 'OPEN' })
          : which === 'verifications'
            ? trustAPI.admin.verifications({ status: 'PENDING' })
            : trustAPI.admin.appeals({ status: 'OPEN' })
      request
        .then((response) => setRows(response.data || []))
        .catch((error) => toast.error(apiErrorMessage(error, t('error'))))
        .finally(() => setLoading(false))
    },
    [t]
  )

  useEffect(() => {
    if (authLoading || !isAuthenticated || !user?.is_staff) {
      setLoading(false)
      return
    }
    loadOverview()
    loadRows(tab)
  }, [
    authLoading,
    isAuthenticated,
    user?.is_staff,
    tab,
    loadOverview,
    loadRows,
  ])

  const refresh = () => {
    loadOverview()
    loadRows(tab)
    toast.success(t('updated'))
  }

  const act = async (id, request) => {
    setBusyId(id)
    try {
      const response = await request()
      setRows((prev) => prev.filter((row) => row.id !== response.data.id))
      loadOverview()
      toast.success(t('updated'))
    } catch (error) {
      toast.error(apiErrorMessage(error, t('error')))
    } finally {
      setBusyId(null)
    }
  }

  if (authLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <LoadingSpinner />
      </div>
    )
  }

  if (!isAuthenticated || !user?.is_staff) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <ShieldCheck className="mx-auto mb-4 h-10 w-10 text-gray-400" />
        <p className="text-gray-600">{t('forbidden')}</p>
        <Link
          href="/"
          className="mt-4 inline-block text-primary hover:underline"
        >
          MarketHub
        </Link>
      </div>
    )
  }

  const cards = [
    { key: 'openReports', value: overview?.open_reports, icon: Flag },
    {
      key: 'overdueReports',
      value: overview?.overdue_reports,
      icon: AlertTriangle,
    },
    {
      key: 'pendingVerifications',
      value: overview?.pending_verifications,
      icon: ShieldCheck,
    },
    { key: 'openAppeals', value: overview?.open_appeals, icon: Gavel },
    {
      key: 'activeBlocklist',
      value: overview?.active_blocklist,
      icon: XCircle,
    },
    {
      key: 'flaggedListings',
      value: overview?.listings_flagged,
      icon: AlertTriangle,
    },
  ]

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">{t('title')}</h1>
          <p className="mt-2 text-gray-600">{t('subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={refresh}
          className="inline-flex items-center gap-2 rounded-xl border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          <RefreshCw className="h-4 w-4" />
          {t('updated')}
        </button>
      </header>

      <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {cards.map(({ key, value, icon: Icon }) => (
          <div
            key={key}
            className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm"
          >
            <Icon className="mb-2 h-4 w-4 text-gray-400" />
            <p className="text-2xl font-bold text-gray-900">{value ?? '—'}</p>
            <p className="text-xs text-gray-500">{t(`overview.${key}`)}</p>
          </div>
        ))}
      </div>

      <div className="mb-5 flex gap-2">
        {TABS.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setTab(value)}
            className={`rounded-xl px-4 py-2 text-sm font-semibold ${
              tab === value
                ? 'bg-primary text-white'
                : 'border border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            {t(`tabs.${value}`)}
          </button>
        ))}
      </div>

      {loading ? (
        <LoadingSpinner />
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-gray-100 bg-gray-50 p-4 text-sm text-gray-500">
          {t('empty')}
        </p>
      ) : tab === 'reports' ? (
        <ul className="space-y-3">
          {rows.map((row) => (
            <ReportRow
              key={row.id}
              row={row}
              t={t}
              busy={busyId === row.id}
              onAct={(payload) =>
                act(row.id, () => trustAPI.admin.reportAction(row.id, payload))
              }
            />
          ))}
        </ul>
      ) : tab === 'verifications' ? (
        <ul className="space-y-3">
          {rows.map((row) => (
            <VerificationRow
              key={row.id}
              row={row}
              t={t}
              busy={busyId === row.id}
              onAct={(payload) =>
                act(row.id, () =>
                  trustAPI.admin.verificationAction(row.id, payload)
                )
              }
            />
          ))}
        </ul>
      ) : (
        <ul className="space-y-3">
          {rows.map((row) => (
            <AppealRow
              key={row.id}
              row={row}
              t={t}
              busy={busyId === row.id}
              onAct={(payload) =>
                act(row.id, () => trustAPI.admin.appealAction(row.id, payload))
              }
            />
          ))}
        </ul>
      )}
    </div>
  )
}

function RowShell({ title, subtitle, meta, badge, children }) {
  return (
    <li className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium text-gray-900">{title}</p>
          {subtitle && <p className="text-sm text-gray-600">{subtitle}</p>}
          {meta && <p className="mt-1 text-xs text-gray-400">{meta}</p>}
        </div>
        {badge}
      </div>
      <div className="mt-3">{children}</div>
    </li>
  )
}

function ReportRow({ row, t, busy, onAct }) {
  const [note, setNote] = useState('')
  const [actionTaken, setActionTaken] = useState('')

  return (
    <RowShell
      title={row.reason_label || row.reason}
      subtitle={row.listing_name || row.reported_user_email}
      meta={`${t('reporter')}: ${row.reporter_email} · ${t('dueBy', {
        date: formatDate(row.sla_due_at),
      })}${row.details ? ` · ${row.details}` : ''}`}
      badge={
        row.is_overdue ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-xs font-semibold text-red-700">
            <Clock className="h-3 w-3" />
            {t('overdue')}
          </span>
        ) : null
      }
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder={t('resolutionPlaceholder')}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <select
          value={actionTaken}
          onChange={(event) => setActionTaken(event.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        >
          {REPORT_ACTIONS.map((value) => (
            <option key={value} value={value}>
              {value === ''
                ? t('noAction')
                : value === 'listing_removed'
                  ? t('removeListing')
                  : value === 'user_banned'
                    ? t('banUser')
                    : t('suspendUser')}
            </option>
          ))}
        </select>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              onAct({
                action: 'dismiss',
                resolution: note.trim(),
                action_taken: actionTaken,
              })
            }
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
          >
            {t('dismiss')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              onAct({
                action: 'action',
                resolution: note.trim(),
                action_taken: actionTaken,
              })
            }
            className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60"
          >
            {t('action')}
          </button>
        </div>
      </div>
    </RowShell>
  )
}

function VerificationRow({ row, t, busy, onAct }) {
  const [note, setNote] = useState('')

  return (
    <RowShell
      title={`${row.kind_label || row.kind} — ${row.store_name || `#${row.user}`}`}
      subtitle={row.document_type}
      meta={formatDate(row.submitted_at)}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder={t('resolutionPlaceholder')}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => onAct({ action: 'reject', reason: note.trim() })}
            className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
          >
            <XCircle className="h-4 w-4" />
            {t('reject')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onAct({ action: 'approve' })}
            className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
          >
            <CheckCircle className="h-4 w-4" />
            {t('approve')}
          </button>
        </div>
      </div>
    </RowShell>
  )
}

function AppealRow({ row, t, busy, onAct }) {
  const [note, setNote] = useState('')

  return (
    <RowShell
      title={`${row.kind_label || row.kind} — ${row.listing_name || row.user_email}`}
      subtitle={row.message}
      meta={formatDate(row.created_at)}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder={t('resolutionPlaceholder')}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => onAct({ action: 'reject', resolution: note.trim() })}
            className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
          >
            <XCircle className="h-4 w-4" />
            {t('reject')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              onAct({ action: 'approve', resolution: note.trim() })
            }
            className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
          >
            <CheckCircle className="h-4 w-4" />
            {t('approve')}
          </button>
        </div>
      </div>
    </RowShell>
  )
}
