// Journey 5 — the Phase 15 `/search` page (docs/todo.md).
// Mirrors search-listing.spec.js but exercises the new advanced endpoint:
// typo-tolerant FTS, facets/sorts and zero-result recovery actions. The
// fixture pins `mh_locale=en`.
const { test, expect } = require('./fixtures')

const SEEDED_PRODUCT = 'E2E Test Phone'

test.describe('advanced search page', () => {
  test('finds the seeded listing through /search', async ({ page }) => {
    await page.goto('/search')

    await expect(page.getByRole('heading', { name: 'Search' })).toBeVisible()

    const searchInput = page.getByPlaceholder(
      'Search products, brands or categories...'
    )
    await searchInput.fill(SEEDED_PRODUCT)
    await searchInput.press('Enter')

    const card = page.getByRole('heading', {
      name: SEEDED_PRODUCT,
      exact: true,
    })
    await expect(card).toBeVisible()
    await expect(page.getByText(/result/i).first()).toBeVisible()

    // Sort control and signed-out save affordance are part of the page shell.
    await expect(page.getByRole('combobox', { name: 'Sort by' })).toBeVisible()
    await expect(
      page.getByRole('link', { name: 'Sign in to save' })
    ).toBeVisible()

    // Clicking the card still lands on the canonical listing detail page.
    await card.click()
    await expect(page).toHaveURL(/\/l\/.+-\d+/)
    await expect(
      page.getByRole('heading', { name: SEEDED_PRODUCT, exact: true }).first()
    ).toBeVisible()
  })

  test('shows recovery guidance instead of a dead end', async ({ page }) => {
    await page.goto('/search')

    const searchInput = page.getByPlaceholder(
      'Search products, brands or categories...'
    )
    await searchInput.fill('zzzz-no-such-listing-zzzz')
    await searchInput.press('Enter')

    await expect(
      page.getByRole('heading', { name: 'No listings found' })
    ).toBeVisible()
    // The page always offers a way out, even when the backend has no
    // did-you-mean/nearby suggestions for this query.
    await expect(
      page.getByRole('button', { name: 'Clear filters' }).first()
    ).toBeVisible()
  })
})
