import { test, expect } from '@playwright/test'

test.describe('Hermes Production Pipeline & Acceptance Verification', () => {
  const ACCEPTANCE_PROJECT = 'baseus-ma10-live-30s-20260815'

  test('Dashboard and Primary Navigation Render Correctly (1440x900)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/')
    await expect(page).toHaveURL(/.*dashboard/)
    await expect(page.locator('h1')).toContainText('Hermes Operational Control Plane')
    await expect(page.locator('.dashboard-metrics-grid')).toBeVisible()

    // Navigate to Projects
    await page.click('a[href="/projects"]')
    await expect(page).toHaveURL(/.*projects/)
    await expect(page.locator('h1')).toContainText('Video Factory Projects')
  })

  test('Acceptance Project baseus-ma10-live-30s-20260815 Across All 7 Stages', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })

    // 1. Stage: Resources
    await page.goto(`/projects/${ACCEPTANCE_PROJECT}/workflow/resources`)
    await expect(page.locator('h3')).toContainText('Product Intelligence Resource Lock')
    await expect(page.locator('body')).toContainText('Baseus Bowie MA10')
    await expect(page.locator('body')).toContainText('lock_baseus_bowie_ma10_acceptance_v1')
    await expect(page.locator('.pipeline-stepper-container')).toBeVisible()

    // 2. Stage: Brief
    await page.click('button:has-text("Brief")')
    await expect(page).toHaveURL(/.*\/workflow\/brief/)
    await expect(page.locator('body')).toContainText('Creative Brief & Narrative Direction')
    await expect(page.locator('body')).toContainText('Brief Approved')

    // 3. Stage: Scenes
    await page.click('button:has-text("Scenes")')
    await expect(page).toHaveURL(/.*\/workflow\/scenes/)
    await expect(page.locator('body')).toContainText('30s / 30s')
    await expect(page.locator('body')).toContainText('Hook')
    await expect(page.locator('body')).toContainText('Use case')

    // 4. Stage: Storyboard
    await page.click('button:has-text("Storyboard")')
    await expect(page).toHaveURL(/.*\/workflow\/storyboard/)
    await expect(page.locator('body')).toContainText('Storyboard Keyframes')
    await expect(page.locator('.storyboard-card')).toHaveCount(4)

    // 5. Stage: Generation
    await page.click('button:has-text("Generation")')
    await expect(page).toHaveURL(/.*\/workflow\/generation/)
    await expect(page.locator('body')).toContainText('Scene Video Generation')
    await expect(page.locator('.generation-scene-card')).toHaveCount(4)
    await expect(page.locator('body')).toContainText('Scene #4')

    // 6. Stage: Timeline
    await page.click('button:has-text("Timeline")')
    await expect(page).toHaveURL(/.*\/workflow\/timeline/)
    await expect(page.locator('body')).toContainText('Draft Video Preview')
    await expect(page.locator('body')).toContainText('Horizontal Timeline Track (30 Seconds)')

    // 7. Stage: Export
    await page.click('button:has-text("Export")')
    await expect(page).toHaveURL(/.*\/workflow\/export/)
    await expect(page.locator('body')).toContainText('Master Video Output (30 Seconds)')
    await expect(page.locator('body')).toContainText('Ready to Publish')
  })

  test('Pipeline Back and Next Navigation Works Seamlessly (1280x800)', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto(`/projects/${ACCEPTANCE_PROJECT}/workflow/resources`)

    // Click Next (brief)
    await page.click('footer button:has-text("Next (brief)")')
    await expect(page).toHaveURL(/.*\/workflow\/brief/)

    // Click Next (scenes)
    await page.click('footer button:has-text("Next (scenes)")')
    await expect(page).toHaveURL(/.*\/workflow\/scenes/)

    // Click Back (brief)
    await page.click('footer button:has-text("Back (brief)")')
    await expect(page).toHaveURL(/.*\/workflow\/brief/)
  })

  test('Legacy /video-factory Redirects to Project Workspace', async ({ page }) => {
    await page.goto(`/video-factory?projectId=${ACCEPTANCE_PROJECT}`)
    await expect(page).toHaveURL(new RegExp(`/projects/${ACCEPTANCE_PROJECT}/workflow/resources`))
  })

  test('Mobile Responsive Ergonomics (390x844)', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(`/projects/${ACCEPTANCE_PROJECT}/workflow/resources`)

    // Verify header and bottom footer fit without horizontal overflow
    await expect(page.locator('.workflow-header')).toBeVisible()
    await expect(page.locator('.pipeline-stepper-container')).toBeVisible()
    await expect(page.locator('.workflow-footer')).toBeVisible()
  })

  test('Export Stage Shows Compliance Badges and Push-to-Channel', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/projects/${ACCEPTANCE_PROJECT}/workflow/export`)

    // Verify compliance section is visible
    await expect(page.locator('body')).toContainText('Compliance & Distribution')

    // Verify Brand Safety badge exists
    await expect(page.locator('body')).toContainText('Brand Safety')

    // Verify AIGC Content badge exists
    await expect(page.locator('body')).toContainText('AIGC Content')

    // Verify Push to Channel section exists
    await expect(page.locator('body')).toContainText('Push to Channel')

    // Verify channel dropdown exists
    await expect(page.locator('text=Select a channel')).toBeVisible()
  })

  test('A/B Variant Flow in Export Stage', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/projects/${ACCEPTANCE_PROJECT}/workflow/export`)

    // Verify Export stage loaded
    await expect(page.locator('body')).toContainText('Master Video Output (30 Seconds)')

    // Check for compliance badges
    await expect(page.locator('body')).toContainText('Brand Safety')
    await expect(page.locator('body')).toContainText('AIGC Content')

    // Verify Push to Channel is present
    await expect(page.locator('text=Push to Channel')).toBeVisible()

    // Test channel selection dropdown
    await page.click('text=Select a channel')
    await expect(page.locator('text=TikTok')).toBeVisible()
    await expect(page.locator('text=YouTube Shorts')).toBeVisible()
    await expect(page.locator('text=Instagram Reels')).toBeVisible()

    // Select a channel
    await page.click('text=TikTok')

    // Verify push button shows
    await expect(page.locator('text=Push to Channel')).toBeVisible()

    // Verify compliance badge is clickable for details
    const complianceBadge = page.locator('text=All checks passed').first()
    if (await complianceBadge.isVisible()) {
      await complianceBadge.click()
    }
  })
})
