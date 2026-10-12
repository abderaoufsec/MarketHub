/**
 * Register page — the Phase 8 phone-first sign-up contract of docs/todo.md:
 *
 * 1. **Email is optional.** A phone-only signup must reach the backend with
 *    the SMS code (`otp_code`) — without it the API refuses the account, so
 *    the page blocks the submit rather than burning a round trip.
 * 2. **The OTP travels with the signup.** `/auth/phone/verify/` is for
 *    signed-in accounts; anonymous verification happens inside the
 *    registration call, so the code is collected (not consumed) here.
 * 3. **The success copy is honest.** Accounts created with an email keep the
 *    exact sentence the e2e suite asserts; phone-only accounts are never told
 *    to "check your email".
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import RegisterPage from './page'

const { mocks } = vi.hoisted(() => ({
  mocks: {
    push: vi.fn(),
    register: vi.fn(),
    requestPhoneOtp: vi.fn(),
    toastSuccess: vi.fn(),
    toastError: vi.fn(),
  },
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push }),
  useSearchParams: () => new URLSearchParams(''),
}))

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ register: mocks.register }),
}))

vi.mock('../../lib/api', () => ({
  authAPI: { requestPhoneOtp: mocks.requestPhoneOtp },
}))

vi.mock('react-hot-toast', () => ({
  default: { success: mocks.toastSuccess, error: mocks.toastError },
}))

const VALID = {
  first_name: 'Yacine',
  last_name: 'Bensalem',
  username: 'yacine',
  password: 'S3cure!Passw0rd',
  password_confirm: 'S3cure!Passw0rd',
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.register.mockResolvedValue({ success: true, data: {} })
})

function fill(overrides = {}) {
  const values = { ...VALID, email: '', phone_number: '', ...overrides }
  for (const [label, value] of Object.entries({
    'First Name': values.first_name,
    'Last Name': values.last_name,
    Username: values.username,
    Password: values.password,
    'Confirm Password': values.password_confirm,
  })) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
  }
  if (values.email) {
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: values.email },
    })
  }
  if (values.phone_number) {
    fireEvent.change(screen.getByLabelText(/phone number/i), {
      target: { value: values.phone_number },
    })
  }
}

describe('phone-first sign-up', () => {
  it('refuses a phone-only signup before the SMS code has been entered', async () => {
    render(<RegisterPage />)
    fill({ phone_number: '+213555000001' })

    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() =>
      expect(mocks.toastError).toHaveBeenCalledWith(
        'Enter the SMS code sent to your phone'
      )
    )
    expect(mocks.register).not.toHaveBeenCalled()
  })

  it('sends an OTP and submits it with the account', async () => {
    mocks.requestPhoneOtp.mockResolvedValue({ data: { detail: 'Code sent' } })

    render(<RegisterPage />)
    fill({ phone_number: '+213555000002', username: '' })

    fireEvent.click(screen.getByRole('button', { name: /send code/i }))
    await waitFor(() =>
      expect(mocks.requestPhoneOtp).toHaveBeenCalledWith({
        phone_number: '+213555000002',
      })
    )

    fireEvent.change(await screen.findByLabelText(/sms code/i), {
      target: { value: '123456' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() => expect(mocks.register).toHaveBeenCalled())
    const payload = mocks.register.mock.calls[0][0]
    expect(payload.otp_code).toBe('123456')
    expect(payload.phone_number).toBe('+213555000002')
    // no email -> the username is derived from the number
    expect(payload.username).toBe('213555000002')
  })

  it('shows the phone confirmation instead of "check your email"', async () => {
    mocks.requestPhoneOtp.mockResolvedValue({ data: { detail: 'Code sent' } })

    render(<RegisterPage />)
    fill({ phone_number: '+213555000003' })
    fireEvent.click(screen.getByRole('button', { name: /send code/i }))
    await screen.findByLabelText(/sms code/i)
    fireEvent.change(screen.getByLabelText(/sms code/i), {
      target: { value: '654321' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    await screen.findByText('Registration Successful!')
    expect(
      screen.getByText(/phone number has been verified/i)
    ).toBeInTheDocument()
    expect(screen.queryByText(/check your email/i)).not.toBeInTheDocument()
  })
})

describe('email sign-up (unchanged Phase 1 contract)', () => {
  it('keeps the exact e2e success sentence when an email is given', async () => {
    render(<RegisterPage />)
    fill({ email: 'newbie@example.com' })

    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    await screen.findByText('Registration Successful!')
    expect(
      screen.getByText('Please check your email to verify your account.')
    ).toBeInTheDocument()
    expect(mocks.register).toHaveBeenCalledWith(
      expect.objectContaining({ email: 'newbie@example.com' })
    )
  })

  it('rejects a signup with neither identifier', async () => {
    render(<RegisterPage />)
    fill()

    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() =>
      expect(mocks.toastError).toHaveBeenCalledWith(
        'Provide an email address or a phone number'
      )
    )
    expect(mocks.register).not.toHaveBeenCalled()
  })
})
