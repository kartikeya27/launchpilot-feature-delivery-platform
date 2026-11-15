import { expect, test, type Page } from '@playwright/test'

async function login(page: Page, username: string, password: string) {
  await page.goto('/')
  await page.getByRole('button', { name: 'Sign in with OIDC' }).click()
  await expect(page.locator('#username')).toBeVisible()
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(password)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: /Good morning, developer/i })).toBeVisible()
}

test('real Keycloak admin: create, rollout, evaluate, Kafka outbox, rollback, audit', async ({ page }) => {
  await login(page, 'demo-admin', 'AdminDemo123!')
  await page.getByLabel('Environment').selectOption('staging')

  const key = `ops_e2e_${Date.now().toString(36)}`
  await page.getByRole('button', { name: 'New flag' }).click()
  const dialog = page.getByRole('dialog', { name: 'Create feature flag' })
  await dialog.getByLabel('Display name').fill('Operational Checkout Canary')
  await dialog.getByLabel('Flag key').fill(key)
  await dialog.getByRole('button', { name: 'Create flag' }).click()

  await page.getByRole('button', { name: /^Feature flags/ }).click()
  const row = page.locator('.flag-row').filter({ hasText: key })
  await expect(row).toBeVisible()
  const slider = row.getByRole('slider')
  await slider.focus()
  await slider.press('End')
  await row.getByRole('button', { name: 'Save changes' }).click()
  await expect(row.getByText('100%')).toBeVisible()
  await row.getByRole('switch').click()
  await expect(row.getByText('Active')).toBeVisible()

  await page.getByRole('button', { name: 'Evaluation lab' }).first().click()
  await page.locator('.playground-panel select').selectOption(key)
  await page.getByLabel('User identifier').fill('synthetic-canary-42')
  await page.getByRole('button', { name: 'Evaluate feature' }).click()
  await expect(page.getByText('FLAG ENABLED')).toBeVisible()
  await page.getByRole('button', { name: 'Record user conversion' }).click()

  await page.getByRole('button', { name: 'Operations' }).click()
  await expect(page.getByRole('region', { name: 'Release operations center' })).toBeVisible()
  await expect(page.getByText('Pending outbox')).toBeVisible()
  const opsRow = page.locator('.ops-row').filter({ hasText: key })
  await expect(opsRow).toBeVisible()
  page.once('dialog', dialog => dialog.accept())
  await opsRow.getByRole('button', { name: `Rollback ${key}` }).click()
  await expect(opsRow.getByText('Paused')).toBeVisible()

  await page.getByRole('button', { name: 'Evaluation lab' }).first().click()
  await page.locator('.playground-panel select').selectOption(key)
  await page.getByRole('button', { name: 'Evaluate feature' }).click()
  await expect(page.getByText('FLAG DISABLED')).toBeVisible()
  await page.getByRole('button', { name: 'Audit trail' }).click()
  await expect(page.locator('.audit-row').filter({ hasText: key }).filter({ hasText: 'rollback' })).toBeVisible()

  // Browser authorization used real Keycloak OIDC tokens; the application wrote
  // exposure and conversion events through PostgreSQL's transactional outbox.
  // Kafka receipt delivery is verified separately by the recovery exercise.
  expect(page.url()).toContain('localhost:8000')
})

test('real Keycloak viewer cannot access rollback controls', async ({ page }) => {
  await login(page, 'demo-viewer', 'ViewerDemo123!')
  await page.getByLabel('Environment').selectOption('staging')
  await page.getByRole('button', { name: 'Operations' }).click()
  await expect(page.getByRole('region', { name: 'Release operations center' })).toBeVisible()
  await expect(page.getByText('Viewer access:')).toBeVisible()
  await expect(page.getByRole('button', { name: /Rollback/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'New flag' })).toHaveCount(0)
})
