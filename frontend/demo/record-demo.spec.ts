import { expect, test, type Page } from '@playwright/test'

/**
 * Public product demo recorded on the disposable local Compose stack.
 * All identities, flags and events are synthetic, and the recording never
 * demonstrates a real automatic SLO breach or cloud deployment.
 */
async function scene(page: Page, title: string, duration = 1600) {
  await page.evaluate((label) => {
    let banner = document.getElementById('launchpilot-demo-caption')
    if (!banner) {
      banner = document.createElement('div')
      banner.id = 'launchpilot-demo-caption'
      Object.assign(banner.style, {
        position: 'fixed', bottom: '22px', right: '22px', zIndex: '2147483647',
        maxWidth: '480px', color: '#ffffff', background: 'rgba(20, 18, 49, .94)',
        padding: '15px 19px', border: '1px solid #9a92ec', borderRadius: '12px',
        boxShadow: '0 15px 38px rgba(0, 0, 0, .4)',
        fontFamily: 'system-ui, sans-serif', fontSize: '17px', fontWeight: '600',
        lineHeight: '1.45', pointerEvents: 'none',
      })
      document.body.appendChild(banner)
    }
    banner.textContent = label
  }, title)
  await page.waitForTimeout(duration) // Deliberate, short holds for a watchable video
}

test('record a verified checkout rollout and manual recovery walkthrough', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Sign in with OIDC' }).click()
  await expect(page.locator('#username')).toBeVisible()
  await page.locator('#username').fill('demo-admin')
  await page.locator('#password').fill('AdminDemo123!')
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: /Good morning, developer/i })).toBeVisible()

  await scene(page, '01 / 06  •  Keycloak OIDC login and admin-only release controls', 2200)
  await page.getByLabel('Environment').selectOption('staging')
  const key = `portfolio_checkout_${Date.now().toString(36)}`

  await scene(page, '02 / 06  •  Create a staging-only checkout feature flag')
  await page.getByRole('button', { name: 'New flag' }).click()
  const dialog = page.getByRole('dialog', { name: 'Create feature flag' })
  await dialog.getByLabel('Display name').fill('Checkout Canary — Product Demo')
  await dialog.getByLabel('Flag key').fill(key)
  await dialog.getByRole('button', { name: 'Create flag' }).click()
  await page.getByRole('button', { name: /^Feature flags/ }).click()
  const row = page.locator('.flag-row').filter({ hasText: key })
  await expect(row).toBeVisible()

  await scene(page, '03 / 06  •  Progressive rollout: 10% first, then 100% for a deterministic demo')
  const slider = row.getByRole('slider')
  await slider.focus()
  await slider.press('Home')
  await slider.press('ArrowRight')
  await slider.press('ArrowRight')
  await expect(row.getByText('10%')).toBeVisible()
  await row.getByRole('button', { name: 'Save changes' }).click()
  await expect(row.getByText('10%')).toBeVisible()
  await page.waitForTimeout(1100)
  await slider.focus()
  await slider.press('End')
  await row.getByRole('button', { name: 'Save changes' }).click()
  await expect(row.getByText('100%')).toBeVisible()
  await row.getByRole('switch').click()
  await expect(row.getByText('Active')).toBeVisible()

  await scene(page, '04 / 06  •  SHA-256 user evaluation and synthetic conversion', 1900)
  await page.getByRole('button', { name: 'Evaluation lab' }).first().click()
  await page.locator('.playground-panel select').selectOption(key)
  await page.getByLabel('User identifier').fill('synthetic-demo-user-42')
  await page.getByRole('button', { name: 'Evaluate feature' }).click()
  await expect(page.getByText('FLAG ENABLED')).toBeVisible()
  await page.waitForTimeout(1100)
  await page.getByRole('button', { name: 'Record user conversion' }).click()

  await scene(page, '05 / 06  •  PostgreSQL outbox → Kafka publisher → deduplicated receipt', 2000)
  await page.getByRole('button', { name: 'Operations' }).click()
  await expect(page.getByRole('region', { name: 'Release operations center' })).toBeVisible()
  await page.getByRole('button', { name: 'Refresh status' }).click()
  await expect(page.getByText('Pending outbox')).toBeVisible()
  await expect(page.getByText('Consumer receipts')).toBeVisible()
  const opsRow = page.locator('.ops-row').filter({ hasText: key })
  await expect(opsRow).toBeVisible()
  await page.waitForTimeout(1700)

  await scene(page, '06 / 06  •  Audited manual rollback; automatic SLO checks are opt-in', 2000)
  page.once('dialog', d => d.accept())
  await opsRow.getByRole('button', { name: `Rollback ${key}` }).click()
  await expect(opsRow.getByText('Paused')).toBeVisible()
  await page.getByRole('button', { name: 'Audit trail' }).click()
  await expect(page.locator('.audit-row').filter({ hasText: key }).filter({ hasText: 'rollback' })).toBeVisible()
  await scene(page, 'Complete  •  Verified local workflow; not a public cloud deployment', 2900)
})
