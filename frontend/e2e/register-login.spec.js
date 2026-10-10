// Journey 1 — register -> login (docs/todo.md Phase 4).
// Registration creates an *unverified* account (login rejects it with 403),
// so the journey registers a fresh user to prove the flow works end-to-end,
// then logs in with the pre-verified account seeded by `manage.py seed_e2e`.
const { test, expect } = require('@playwright/test')

const BUYER = {
  email: 'e2e-buyer@example.com',
  password: 'E2e!SmokeTest123',
  firstName: 'E2E',
}

test.describe('register and login', () => {
  test('a new user can register and sees the verification notice', async ({
    page,
  }) => {
    const stamp = Date.now()
    await page.goto('/register')

    await page.getByLabel('First Name').fill('Test')
    await page.getByLabel('Last Name').fill(`User${stamp}`)
    await page.getByLabel('Email address').fill(`newbie${stamp}@example.com`)
    await page.getByLabel('Username').fill(`newbie${stamp}`)
    await page.getByLabel('Password', { exact: true }).fill('S3cure!Passw0rd')
    await page.getByLabel('Confirm password').fill('S3cure!Passw0rd')

    await page.getByRole('button', { name: 'Create account' }).click()

    await expect(
      page.getByRole('heading', { name: 'Registration Successful!' })
    ).toBeVisible()
    await expect(
      page.getByText('Please check your email to verify your account.', {
        exact: true,
      })
    ).toBeVisible()
  })

  test('a verified user can log in and is greeted in the header', async ({
    page,
  }) => {
    await page.goto('/login')

    await page.getByPlaceholder('Email address').fill(BUYER.email)
    await page.getByPlaceholder('Password').fill(BUYER.password)
    await page.getByRole('button', { name: 'Sign in' }).click()

    // AuthContext stores the JWT cookies and the header greets the user.
    // The Logout control lives in the user dropdown, which only opens on hover.
    await expect(page.getByText(BUYER.firstName).first()).toBeVisible()
    await page.getByRole('button', { name: BUYER.firstName }).hover()
    await expect(page.getByRole('button', { name: 'Logout' })).toBeVisible()
  })

  test('login rejects wrong credentials', async ({ page }) => {
    await page.goto('/login')

    await page.getByPlaceholder('Email address').fill(BUYER.email)
    await page.getByPlaceholder('Password').fill('definitely-wrong')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByText(/invalid|failed|incorrect/i).first()).toBeVisible()
    // still on the login page
    await expect(page).toHaveURL(/\/login/)
  })
})
