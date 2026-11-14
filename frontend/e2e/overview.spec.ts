import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('dashboard and feature flag evaluation work end to end', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /Good morning, developer/i })).toBeVisible()
  await page.getByRole('button', { name: /Evaluation lab/i }).first().click()
  await page.getByRole('button', { name: 'Evaluate feature', exact: true }).click()
  await expect(page.getByText('DECISION RESPONSE')).toBeVisible()
  await expect(page.getByText('HTTP 200')).toBeVisible()
})

test('@a11y critical WCAG accessibility violations', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /Good morning/i })).toBeVisible()
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  expect(results.violations.filter(v => v.impact === 'critical' || v.impact === 'serious')).toEqual([])
})
