// Journey 2 — post a listing (docs/todo.md Phase 4).
// Logs in as the pre-verified seller seeded by `manage.py seed_e2e`, lands on
// /seller/dashboard, then publishes a product through /seller/products/create
// and waits for the success message + redirect to "My Products".
// The name is stamped per run so repeated runs never collide; the seed command
// prunes stale "E2E Listing ..." rows so the free-plan quota is never hit.
const { test, expect } = require('@playwright/test')

const SELLER = {
  email: 'e2e-seller@example.com',
  password: 'E2e!SmokeTest123',
}

test.describe('post a listing', () => {
  test('a seller can publish a product from the create form', async ({
    page,
  }) => {
    const stamp = Date.now()
    const name = `E2E Listing ${stamp}`

    // Sign in — sellers are redirected to their dashboard.
    await page.goto('/login')
    await page.getByPlaceholder('Email address').fill(SELLER.email)
    await page.getByPlaceholder('Password').fill(SELLER.password)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL(/\/seller\/dashboard/)
    await expect(page.getByText('Seller Dashboard').first()).toBeVisible()

    // Fill in the create-product form.
    await page.goto('/seller/products/create')
    await expect(
      page.getByRole('heading', { name: 'Add New Product' })
    ).toBeVisible()

    await page.getByLabel(/Product Name/).fill(name)
    await page
      .getByLabel('Description')
      .fill('A phone listed by the Playwright smoke journey.')
    await page.getByLabel(/Price/).fill('99.50')
    await page.getByLabel('Category').fill('phones')

    await page.getByRole('button', { name: 'Create Product' }).click()

    // Success message, then the page redirects to the product list.
    await expect(
      page.getByText('Product created successfully!')
    ).toBeVisible()
    await expect(page).toHaveURL(/\/seller\/products/)
    await expect(
      page.getByRole('heading', { name: 'My Products' })
    ).toBeVisible()
    await expect(page.getByText(name).first()).toBeVisible()
  })
})
