import { defineConfig, devices } from '@playwright/test'

/** Real Docker Compose stack: PostgreSQL, Redis, Kafka, Keycloak and OIDC-built SPA.
 * The stack is launched by GitHub Actions or the developer, not Playwright webServer.
 */
export default defineConfig({
  testDir: './fullstack',
  timeout: 90_000,
  expect: { timeout: 25_000 },
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://localhost:8000',
    trace: 'on',
    screenshot: 'on',
    video: 'on',
  },
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list'], ['html', { open: 'never' }]],
})
