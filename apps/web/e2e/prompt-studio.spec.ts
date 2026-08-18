import { test, expect } from '@playwright/test'

test('Prompt Studio loads and displays project context', async ({ page }) => {
  await page.goto('/projects/baseus-ma10-live-30s-20260815/prompt-studio')
  await expect(page.locator('h1')).toContainText('Prompt Studio')
})