/**
 * Saved searches page — Phase 15 management surface.
 *
 * The backend stores the canonical query string, so "open" is a plain link.
 * These tests pin the two mutations users actually perform (pause/resume and
 * delete) and the signed-out contract.
 */

import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithIntl } from '../../../test/i18n'
import SavedSearchesPage from './page'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    savedList: vi.fn(),
    updateSaved: vi.fn(),
    deleteSaved: vi.fn(),
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
    auth: { isAuthenticated: true, loading: false },
  },
}))

vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => mocks.auth,
}))

vi.mock('../../../lib/api', () => ({
  searchAPI: {
    savedList: mocks.savedList,
    updateSaved: mocks.updateSaved,
    deleteSaved: mocks.deleteSaved,
  },
}))

vi.mock('react-hot-toast', () => ({
  default: { success: mocks.toastSuccess, error: mocks.toastError },
}))

const ROW = {
  id: 7,
  name: 'Phones in Algiers',
  query_string: 'q=phone&wilaya=16',
  params: { q: 'phone', wilaya: '16' },
  frequency: 'DAILY',
  is_active: true,
  notify_email: true,
  notify_sms: false,
  notify_whatsapp: true,
  last_notified_at: '2026-11-01T09:30:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.auth = { isAuthenticated: true, loading: false }
  mocks.savedList.mockResolvedValue({ data: [ROW] })
  mocks.updateSaved.mockResolvedValue({
    data: { ...ROW, is_active: false },
  })
  mocks.deleteSaved.mockResolvedValue({ data: null })
})

describe('saved searches page', () => {
  it('lists saved searches with their channels and last alert', async () => {
    renderWithIntl(<SavedSearchesPage />)

    expect(await screen.findByText('Phones in Algiers')).toBeInTheDocument()
    expect(screen.getByText('q=phone&wilaya=16')).toBeInTheDocument()
    expect(screen.getByText('Daily')).toBeInTheDocument()
    expect(screen.getByText('Email')).toBeInTheDocument()
    expect(screen.getByText('WhatsApp')).toBeInTheDocument()
    expect(screen.getByText(/Last alert:/)).toBeInTheDocument()
  })

  it('pauses a search and reflects the new state', async () => {
    renderWithIntl(<SavedSearchesPage />)
    await screen.findByText('Phones in Algiers')

    fireEvent.click(screen.getByRole('button', { name: 'Pause alerts' }))

    await waitFor(() =>
      expect(mocks.updateSaved).toHaveBeenCalledWith(7, { is_active: false })
    )
    expect(await screen.findByText('Paused')).toBeInTheDocument()
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Paused')
  })

  it('deletes after confirmation and removes the row', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithIntl(<SavedSearchesPage />)
    await screen.findByText('Phones in Algiers')

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(mocks.deleteSaved).toHaveBeenCalledWith(7))
    await waitFor(() =>
      expect(screen.queryByText('Phones in Algiers')).not.toBeInTheDocument()
    )
    expect(
      screen.getByText('You have no saved searches yet.')
    ).toBeInTheDocument()
    expect(mocks.toastSuccess).toHaveBeenCalledWith('Saved search deleted.')
  })

  it('asks signed-out visitors to sign in instead of rendering an empty list', async () => {
    mocks.auth = { isAuthenticated: false, loading: false }
    renderWithIntl(<SavedSearchesPage />)

    expect(
      await screen.findByText('Sign in to manage your saved searches.')
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute(
      'href',
      '/login?next=/profile/saved-searches'
    )
    expect(mocks.savedList).not.toHaveBeenCalled()
  })
})
