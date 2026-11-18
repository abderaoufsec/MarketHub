// Journey 7 — Phase 17 trust & safety.
//
// Covers the three surfaces a normal account touches: the public safety
// centre, the seller verification page and reporting a listing from its
// detail page. The staff queue is exercised by the API tests and renders only
// for `is_staff` accounts, which the E2E seed does not create.
const { test, expect } = require('./fixtures')

const BUYER = {
  email: 'e2e-buyer@example.com',
  password: 'E2e!SmokeTest123',
  name: 'E2E',
}

const LISTING = 'E2E Negotiable Phone'
const FRONTEND_URL = process.env.E2E_FRONTEND_URL || 'http://localhost:3000'

async function login(page) {
  await page.goto('/login')
  await page.getByPlaceholder('Email address').fill(BUYER.email)
  await page.getByPlaceholder('Password').fill(BUYER.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: BUYER.name })).toBeVisible()
}

async function openListing(page) {
  await page.goto('/search?q=E2E%20Negotiable%20Phone')
  const card = page.getByRole('heading', { name: LISTING, exact: true })
  await expect(card).toBeVisible()
  await card.click()
  await expect(
    page.getByRole('heading', { name: LISTING, exact: true }).first()
  ).toBeVisible()
}

test.describe('trust & safety', () => {
  test('the safety centre is public and localised', async ({ page }) => {
    await page.goto('/safety')

    await expect(
      page.getByRole('heading', { name: 'Safety centre', level: 1 })
    ).toBeVisible()
    // The guidance is authored server-side; a handful of sections must render.
    await expect(
      page.getByRole('heading', { name: 'Never pay in advance' })
    ).toBeVisible()
    await expect(
      page.getByRole('heading', { name: 'Keep the conversation on MarketHub' })
    ).toBeVisible()
  })

  test('a buyer reports a listing from its detail page', async ({ page }) => {
    await login(page)
    await openListing(page)

    await page.getByRole('button', { name: 'Report', exact: true }).click()
    await expect(
      page.getByRole('heading', { name: 'Report', exact: true })
    ).toBeVisible()

    await page.getByRole('combobox').selectOption('COUNTERFEIT')
    await page
      .getByPlaceholder('Describe the problem...')
      .fill('The photos look copied from another shop.')
    await page.getByRole('button', { name: 'Send report' }).click()

    await expect(
      page.getByText('Thanks - our team will review this report.')
    ).toBeVisible()
  })

  test('a signed-in user opens their verification page', async ({ page }) => {
    await login(page)
    await page.goto('/profile/verification')

    await expect(
      page.getByRole('heading', { name: 'Seller verification', level: 1 })
    ).toBeVisible()
    await expect(
      page.getByRole('heading', { name: 'Verify my identity' })
    ).toBeVisible()
  })
})

// The locale cookie is set by the shared fixture; keep the constant referenced
// so an environment override remains obvious to future readers.
void FRONTEND_URL
