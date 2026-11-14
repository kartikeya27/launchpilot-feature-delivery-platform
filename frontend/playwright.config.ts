import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:5173', trace: process.env.CI ? 'on' : 'retain-on-failure', screenshot: process.env.CI ? 'on' : 'only-on-failure', video: process.env.CI ? 'on' : 'retain-on-failure' },
  webServer: [
    { command: 'python -m uvicorn app.main:app --host 127.0.0.1 --port 8000', cwd: '../backend', url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: !process.env.CI, env: { AUTH_MODE: 'demo', SEED_DEMO: 'true', DATABASE_URL: 'sqlite:///./launchpilot_e2e.db' } },
    { command: 'npm run dev', url: 'http://127.0.0.1:5173', reuseExistingServer: !process.env.CI },
  ],
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
})
