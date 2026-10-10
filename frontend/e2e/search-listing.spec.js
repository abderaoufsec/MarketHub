// Journey 3 — search -> open listing (docs/todo.md Phase 4).
// Uses the listing seeded by `manage.py seed_e2e` ("E2E Test Phone"): search
// for it on /products, open the card, and assert the detail page renders it.
const { test, expect } = require('@playwright/test')

const SEEDED_PRODUCT = 'E2E Test Phone'

test.describe('search and open a listing', () => {
  test('searching finds the seeded listing and its detail page opens', async ({
    page,
  }) => {
    await page.goto('/products')
    await expect(
      page.getByRole('heading', { name: 'Browse Products' })
    ).toBeVisible()

    // Type the query and submit the search form (Enter inside the input).
    const searchInput = page.getByPlaceholder('Search products...')
    await searchInput.fill(SEEDED_PRODUCT)
    await searchInput.press('Enter')

    // Exactly the seeded listing comes back; click through to the detail page.
    const card = page.getByRole('heading', {
      name: SEEDED_PRODUCT,
      exact: true,
    })
    await expect(card).toBeVisible()
    await card.click()

    await expect(page).toHaveURL(/\/products\/\d+/)
    await expect(
      page.getByRole('heading', { level: 1, name: SEEDED_PRODUCT })
    ).toBeVisible()
  })
})
