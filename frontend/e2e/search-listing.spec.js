// Journey 3 — search -> open listing (docs/todo.md Phase 4).
// Uses the listing seeded by `manage.py seed_e2e` ("E2E Test Phone"): search
// for it on /products, open the card, and assert the detail page renders it.
// The shared fixture pins `mh_locale=en` (Phase 11: default UI is French).
const { test, expect } = require('./fixtures')

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

    // Phase 13: the card links to the canonical /l/<slug>-<id> URL, and the
    // detail page normalizes any legacy /products/<id> to the same place.
    await expect(page).toHaveURL(/\/l\/.+-\d+/)
    await expect(
      page.getByRole('heading', { level: 1, name: SEEDED_PRODUCT })
    ).toBeVisible()
  })
})
