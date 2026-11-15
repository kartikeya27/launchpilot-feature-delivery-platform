import { defineConfig, devices } from '@playwright/test'

/** Record a synthetic staging-only portfolio demo against the real local Compose stack. */
export default defineConfig({
  testDir: './portfolio',
  timeout: 120_000,
  expect: { timeout: 25_000 },
  workers: 1,
  retries: 0,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://localhost:8000',
    viewport: { width: 1440, height: 900 },
    video: 'on',
    trace: 'on',
    screenshot: 'on',
  },
  reporter: process.env.CI
    ? [['github'], ['html', { open: 'never' }]]
    : [['list'], ['html', { open: 'never' }]],
})
