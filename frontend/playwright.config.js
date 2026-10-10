// Playwright config — 3 smoke journeys from docs/todo.md Phase 4:
//   1. register -> login
//   2. post a listing (seller)
//   3. search -> open listing
//
// Both servers are started automatically (webServer). The backend must be
// reachable with a migrated database; run `python manage.py seed_e2e` once
// (the globalSetup does it for you) to create the verified buyer/seller.
const { defineConfig, devices } = require('@playwright/test')

const BACKEND_URL = process.env.E2E_BACKEND_URL || 'http://localhost:8000'
const FRONTEND_URL = process.env.E2E_FRONTEND_URL || 'http://localhost:3000'

module.exports = defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  // The smoke suite shares one seeded database; keep it serial and restart
  // the browser context between specs so cookies do not leak.
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: FRONTEND_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: 'python manage.py runserver 127.0.0.1:8000 --noreload',
      cwd: '../backend',
      url: `${BACKEND_URL}/api/products/`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: 'npm run dev',
      url: FRONTEND_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
  globalSetup: './e2e/global-setup.js',
})
