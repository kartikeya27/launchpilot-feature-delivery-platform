import { expect, test } from '@playwright/test'
test('OIDC login prompt (when built in OIDC mode)', async ({ page }) => {
  test.skip(process.env.VITE_AUTH_MODE !== 'oidc', 'OIDC disabled in demo test suite')
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign in with OIDC' })).toBeVisible()
})
