// Journey 6 — Phase 16 contact, chat and offers.
//
// The seed command creates a negotiable classified owned by the seller, with
// a verified phone number. These journeys prove the three contact paths a
// classified now has: an audited phone reveal with native deep links, an
// in-app chat with safety nudges, and a price offer the seller can accept.
// The shared fixture pins `mh_locale=en` (Phase 11: default UI is French).
const { test, expect } = require('./fixtures')

const BUYER = {
  email: 'e2e-buyer@example.com',
  password: 'E2e!SmokeTest123',
  name: 'E2E',
}

const SELLER = {
  email: 'e2e-seller@example.com',
  password: 'E2e!SmokeTest123',
  name: 'E2E',
}

const LISTING = 'E2E Negotiable Phone'
const PHONE = '+213555123456'
const FRONTEND_URL = process.env.E2E_FRONTEND_URL || 'http://localhost:3000'

async function login(page, account) {
  await page.goto('/login')
  await page.getByPlaceholder('Email address').fill(account.email)
  await page.getByPlaceholder('Password').fill(account.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  // The hydrated header user button only renders once the session is known.
  await expect(page.getByRole('button', { name: account.name })).toBeVisible()
}

async function signedInPage(browser, account) {
  const context = await browser.newContext()
  await context.addCookies([
    { name: 'mh_locale', value: 'en', url: FRONTEND_URL },
  ])
  const page = await context.newPage()
  await login(page, account)
  return { context, page }
}

async function openListing(page) {
  await page.goto('/search?q=E2E%20Negotiable%20Phone')
  const card = page.getByRole('heading', { name: LISTING, exact: true })
  await expect(card).toBeVisible()
  await card.click()
  await expect(page).toHaveURL(/\/l\/e2e-negotiable-phone-\d+/)
  await expect(
    page.getByRole('heading', { name: LISTING, exact: true }).first()
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Contact the seller' })
  ).toBeVisible()
}

test.describe('contact, chat and offers', () => {
  test('a buyer reveals a verified phone with safe deep links', async ({
    page,
  }) => {
    await login(page, BUYER)
    await openListing(page)

    // Public payload says only that a number *can* be revealed; the click
    // performs the authenticated, throttled, audited request.
    await expect(page.getByText(PHONE)).toHaveCount(0)
    await page.getByRole('button', { name: 'Show phone number' }).click()

    await expect(page.getByText(PHONE)).toBeVisible()
    await expect(page.locator(`a[href="tel:${PHONE}"]`)).toBeVisible()
    await expect(page.locator(`a[href="sms:${PHONE}"]`)).toBeVisible()
    await expect(
      page.locator('a[href="https://wa.me/213555123456"]')
    ).toBeVisible()
  })

  test('a buyer chats, gets a safety nudge, and the seller accepts an offer', async ({
    browser,
    page,
  }) => {
    const stamp = Date.now()
    const safeMessage = `Hello, is this still available? (${stamp.toString(36)})`
    // A first message cannot contain a phone number; this is the *second*
    // message, so it is delivered with a nudge instead of a rejection.
    const phoneMessage = `Call me on 0${String(stamp).slice(-9)}`
    const conversationPattern = /\/messages\/\d+$/

    await login(page, BUYER)
    await openListing(page)

    await page.getByRole('button', { name: 'Message the seller' }).click()
    await expect(page).toHaveURL(conversationPattern)
    const conversationUrl = new URL(page.url()).pathname

    // First message: normal text goes straight through.
    const composer = page.getByPlaceholder('Write a message...')
    await composer.fill(safeMessage)
    await page.getByRole('button', { name: 'Send' }).click()
    await expect(page.getByText(safeMessage)).toBeVisible()
    // Wait for the send to settle: handleSend clears the draft after the
    // response, and filling too early would race that reset.
    await expect(composer).toHaveValue('')

    // Later messages may share a phone number, but the UI nudges the buyer.
    await composer.fill(phoneMessage)
    await page.getByRole('button', { name: 'Send' }).click()
    await expect(page.getByText(phoneMessage)).toBeVisible()
    await expect(composer).toHaveValue('')
    await expect(
      page.getByText(
        'This message contains a phone number. Keep the deal on MarketHub.'
      )
    ).toBeVisible()

    // Make an offer inline. On a retry an earlier attempt may have left a
    // pending offer behind; withdraw it first so the run is deterministic.
    const withdraw = page.getByRole('button', { name: 'Withdraw' })
    if ((await withdraw.count()) > 0) {
      await withdraw.first().click()
      await expect(page.getByText('Withdrawn').first()).toBeVisible()
    }
    await page.getByRole('button', { name: 'Make an offer' }).click()
    const offerDialog = page.getByRole('dialog')
    await expect(offerDialog).toBeVisible()
    await offerDialog.getByLabel('Your offer (DZD)').fill('20000')
    await offerDialog
      .getByLabel('Message (optional)')
      .fill('I can pick it up today.')
    await offerDialog.getByRole('button', { name: 'Send offer' }).click()
    await expect(page.getByText('Price offer').last()).toBeVisible()
    await expect(
      page.getByText('Pending', { exact: true }).last()
    ).toBeVisible()

    // The seller sees the thread in their inbox with the unread badge.
    const seller = await signedInPage(browser, SELLER)
    try {
      await seller.page.goto('/messages')
      const row = seller.page.getByRole('link', { name: new RegExp(LISTING) })
      await expect(row).toBeVisible()
      await expect(row.getByText(/Offer of 20,000 DZD/)).toBeVisible()
      await expect(row.locator('span.bg-primary').first()).toBeVisible()
      await seller.page.goto(conversationUrl)

      await expect(seller.page.getByText(safeMessage)).toBeVisible()
      await expect(seller.page.getByText('Price offer').last()).toBeVisible()
      await seller.page.getByRole('button', { name: 'Accept' }).last().click()
      await expect(
        seller.page.getByText('Accepted', { exact: true }).last()
      ).toBeVisible()
    } finally {
      await seller.context.close()
    }

    // The buyer's open chat polls and reflects the accepted status.
    await expect(
      page.getByText('Accepted', { exact: true }).last()
    ).toBeVisible({
      timeout: 15_000,
    })
  })
})
