import { test, expect } from '@playwright/test'

test.describe('Hermes Omni Chat Studio E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Mock authenticated server session
    await page.route('**/api/session*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          principal: {
            actor_id: 'authenticated_user',
            owner_user_id: 'authenticated_user',
            platform: 'gui',
            session_id: 'session_123',
            roles: ['user'],
          },
        }),
      })
    })
  })

  test('Omni Chat Studio Page Renders and Shows Initial Assistant Welcome', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/studio')

    // Verify studio header
    await expect(page.locator('h1')).toContainText('Omni Chat Studio')
    await expect(page.locator('body')).toContainText('Runtime Connected')

    // Verify welcome message and prompt templates
    await expect(page.locator('.chat-message-row.assistant')).toBeVisible()
    await expect(page.locator('.suggestions-grid')).toBeVisible()
    await expect(page.locator('button:has-text("Tạo Video Review Tai Nghe")')).toBeVisible()
    await expect(page.locator('button:has-text("Đọc Brand Guidelines")')).toBeVisible()
  })

  test('Product to Video Generation Triggers Live Progress and Video Player', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/studio')

    const textarea = page.locator('.composer-textarea')
    await textarea.fill('Tạo video review cho Anker Soundcore Q30')

    const sendBtn = page.locator('button:has-text("Gửi lệnh")')
    await expect(sendBtn).toBeEnabled()
    await sendBtn.click()

    // Tool execution badge appears
    await expect(page.locator('body')).toContainText('product_to_video')

    // Progress card appears
    await expect(page.locator('body')).toContainText('AI Video Synthesis Pipeline', { timeout: 5000 })

    // Video Player appears once completed
    await expect(page.locator('button:has-text("Open in Workspace")')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('body')).toContainText('9:16 HD')
    await expect(page.locator('body')).toContainText('KEYFRAME ASSETS')
  })

  test('Document Reading Command Renders Tool Badge and Document Preview Card', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/studio')

    const textarea = page.locator('.composer-textarea')
    await textarea.fill('Đọc tài liệu brand guidelines')

    const sendBtn = page.locator('button:has-text("Gửi lệnh")')
    await sendBtn.click()

    // Tool badge and doc preview card appear
    await expect(page.locator('body')).toContainText('read_file', { timeout: 5000 })
    await expect(page.locator('body')).toContainText('Tài liệu tham chiếu', { timeout: 8000 })
  })

  test('Global Quick Omni Chat Drawer Opens and Closes Smoothly', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/dashboard')

    const quickChatBtn = page.locator('button:has-text("Quick Omni Chat")')
    await expect(quickChatBtn).toBeVisible()
    await quickChatBtn.click()

    // Drawer opens
    await expect(page.locator('.omni-drawer-panel')).toBeVisible()
    await expect(page.locator('.omni-drawer-header')).toContainText('Hermes Omni Chat')

    // Close button works
    await page.click('button[aria-label="Close drawer"]')
    await expect(page.locator('.omni-drawer-panel')).not.toBeVisible()
  })
})
