// Journey 5 — post a classified through the Phase 13 wizard (/post).
// Logs in as the seeded *buyer*: individuals post ads without a store and
// without the seller role. Walks the five steps (basics → photos → details →
// location → price & publish) and lands on the canonical /l/<slug>-<id> URL.
// The name is stamped per run; `manage.py seed_e2e` prunes stale "E2E Ad …"
// rows so the free-tier listing quota is never hit. The shared fixture pins
// `mh_locale=en` (Phase 11: default UI is French).
const { test, expect } = require('./fixtures')
const path = require('path')

const BUYER = {
  email: 'e2e-buyer@example.com',
  password: 'E2e!SmokeTest123',
}

// A real JPEG the browser uploads through the Phase 14 pipeline.
const PHOTO = path.join(__dirname, 'fixtures', 'e2e-photo.jpg')

test.describe('post a classified', () => {
  test('an individual can publish an ad in the wizard', async ({ page }) => {
    const stamp = Date.now()
    const name = `E2E Ad ${stamp}`

    // Sign in — the buyer has no store and no dashboard redirect. Wait for
    // the hydrated session (the header user button renders only then): the
    // "Post an ad" link exists on /login too, and clicking it mid-login
    // races the post-login redirect.
    await page.goto('/login')
    await page.getByPlaceholder('Email address').fill(BUYER.email)
    await page.getByPlaceholder('Password').fill(BUYER.password)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('button', { name: 'E2E' })).toBeVisible()

    // Header "Post an ad" — the wizard is not seller-only.
    await page.getByRole('link', { name: 'Post an ad' }).first().click()
    await expect(page).toHaveURL(/\/post/)
    await expect(
      page.getByRole('heading', { name: 'Post an ad' }).first()
    ).toBeVisible()

    // Step 1 — the basics: type (defaults to "For sale"), title, blurb,
    // category. The first Continue creates the draft server-side.
    await page.getByLabel(/^Title/).fill(name)
    await page
      .getByLabel(/^Description/)
      .fill('A bike listed by the Playwright wizard journey.')
    await page
      .getByLabel(/^Category/)
      .selectOption({ label: 'Phones & Tablets' })
    await page.getByRole('button', { name: 'Continue' }).click()

    // Step 2 — photos: upload a real file; the pipeline stores the variants
    // and the grid marks the first photo as the cover.
    await expect(
      page.getByText('Listings with real photos sell faster.')
    ).toBeVisible()
    await page.locator('input[type="file"]').setInputFiles(PHOTO)
    await expect(page.getByText('Cover', { exact: true })).toBeVisible({
      timeout: 60_000,
    })
    await expect(page.locator('img[src*="thumb"]').first()).toBeVisible()
    await page.getByRole('button', { name: 'Continue' }).click()

    // Step 3 — details: the category's attribute fields plus contact mode.
    await expect(page.getByText('How should buyers reach you?')).toBeVisible()
    await expect(page.locator('#attr-brand')).toBeVisible()
    await page.selectOption('#attr-brand', 'samsung')
    await page.selectOption('#attr-storage', '128')
    await page.selectOption('#attr-condition', 'new')
    await page.getByRole('button', { name: 'Continue' }).click()

    // Step 4 — location: the publish gate requires a wilaya.
    await expect(page.getByText('Buyers filter by wilaya')).toBeVisible()
    await page.getByLabel(/^Wilaya/).selectOption({ label: 'Alger' })
    await page.getByRole('button', { name: 'Continue' }).click()

    // Step 5 — price & publish.
    await expect(page.getByRole('button', { name: /^Publish$/ })).toBeVisible()
    await page.getByLabel(/^Price/).fill('12000')
    await page.getByRole('button', { name: /^Publish$/ }).click()

    // Live: the wizard lands on the canonical listing URL, own slug, own id.
    await expect(page).toHaveURL(/\/l\/e2e-ad-\d+-\d+/)
    await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
    // The classified is contact-first — no "Add to Cart" on the page.
    await expect(
      page.getByRole('heading', { name: 'Contact the seller' })
    ).toBeVisible()
    // The uploaded photo is on the public page, as the detail WebP variant
    // (the wizard already proved the `thumb` variant during upload).
    await expect(page.locator('img[src*="full.webp"]').first()).toBeVisible()
  })
})
