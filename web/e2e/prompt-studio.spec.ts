import { test, expect } from '@playwright/test'

test('approval advances one Prompt Studio step and locks the prior snapshot', async ({ page }) => {
  await page.goto('/projects/p-1/prompt-studio')
  await page.getByRole('button', { name: /Duyệt/ }).click()
  await expect(page.getByText('2. Phân tích')).toBeVisible()
  await expect(page.getByLabel('Tên sản phẩm')).toBeDisabled()
})