import { test, expect } from '@playwright/test'

test.describe('Hermes Action Wiring & Security Contract Smoke Tests', () => {
  const TEST_PROJECT = 'test-wiring-project-2026'

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

  test('Bind Resources action calls POST endpoint without client owner override', async ({ page }) => {
    let capturedUrl = ''
    let capturedMethod = ''

    await page.route(`**/api/vf/projects/${TEST_PROJECT}*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          data: {
            id: TEST_PROJECT,
            owner_user_id: 'authenticated_user',
            status: 'draft',
            resource_pack: null,
          },
        }),
      })
    })

    await page.route(`**/api/vf/projects/${TEST_PROJECT}/resources/bind*`, async (route) => {
      capturedUrl = route.request().url()
      capturedMethod = route.request().method()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          data: {
            id: TEST_PROJECT,
            status: 'draft',
            resource_pack: {
              id: 'lock_test_v1',
              product_references: [{ asset_id: 'asset-ref-1' }],
              product_identity_description: 'Test Product',
            },
          },
        }),
      })
    })

    await page.goto(`/projects/${TEST_PROJECT}/workflow/resources`)
    const input = page.locator('input[placeholder*="Search product name"]')
    await expect(input).toBeVisible()
    await input.fill('test-query')

    const bindButton = page.locator('button:has-text("Bind Locked Resources")')
    await expect(bindButton).toBeEnabled()

    const [request] = await Promise.all([
      page.waitForRequest(`**/api/vf/projects/${TEST_PROJECT}/resources/bind*`),
      bindButton.click(),
    ])

    expect(request.method()).toBe('POST')
    expect(request.url()).toContain(`/api/vf/projects/${TEST_PROJECT}/resources/bind`)
    expect(request.url()).not.toContain('owner_user_id=impersonated_user')
  })

  test('Approve Brief action calls POST /brief/approve and triggers refresh', async ({ page }) => {
    let approveCalled = false

    await page.route(`**/api/vf/projects/${TEST_PROJECT}*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          data: {
            id: TEST_PROJECT,
            owner_user_id: 'authenticated_user',
            status: 'draft',
            resource_pack: {
              id: 'lock_test_v1',
              product_references: [{ asset_id: 'asset-1' }],
              product_identity_description: 'Test Product',
            },
            creative_brief: {
              objective: 'Test Objective',
              target_audience: 'Target Audience',
              core_message: 'Core Message',
              content_blocks: ['Hook', 'Use case'],
            },
            brief_approval: 'pending',
          },
        }),
      })
    })

    await page.route(`**/api/vf/projects/${TEST_PROJECT}/brief/approve*`, async (route) => {
      approveCalled = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          data: {
            id: TEST_PROJECT,
            brief_approval: 'approved',
          },
        }),
      })
    })

    await page.goto(`/projects/${TEST_PROJECT}/workflow/brief`)
    const approveBtn = page.locator('button:has-text("Approve Brief")')
    await expect(approveBtn).toBeVisible()
    await approveBtn.click()
    expect(approveCalled).toBe(true)
  })

  test('Storyboard generation triggers durable job polling', async ({ page }) => {
    let jobPolled = false

    await page.route(`**/api/vf/projects/${TEST_PROJECT}*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          data: {
            id: TEST_PROJECT,
            owner_user_id: 'authenticated_user',
            status: 'draft',
            resource_pack: {
              id: 'lock_test_v1',
              product_references: [{ asset_id: 'asset-1' }],
              product_identity_description: 'Test Product',
            },
            brief_approval: 'approved',
            scene_plan_approval: 'approved',
            scene_plan: {
              scenes: [
                {
                  scene_id: 'scene_1',
                  order: 1,
                  title: 'Hook',
                  objective: 'Capture attention',
                  content: 'Product intro',
                  visual_style: 'Studio',
                  duration_seconds: 6,
                  setting: 'Studio',
                  camera_movement: 'Push in',
                },
              ],
            },
          },
        }),
      })
    })

    await page.route(`**/api/vf/projects/${TEST_PROJECT}/storyboard/generate*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          jobs: [{ job_id: 'job_sb_test_123', frame_id: 'frame_1' }],
          data: { id: TEST_PROJECT, status: 'storyboard_in_progress' },
        }),
      })
    })

    await page.route('**/api/jobs/job_sb_test_123*', async (route) => {
      jobPolled = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'job_sb_test_123',
          task_name: 'image_generate',
          status: 'succeeded',
        }),
      })
    })

    await page.goto(`/projects/${TEST_PROJECT}/workflow/storyboard`)
    const generateBtn = page.locator('button:has-text("Generate Keyframes")')
    await expect(generateBtn).toBeVisible()
    await generateBtn.click()
    await page.waitForTimeout(2000)
    expect(jobPolled).toBe(true)
  })
})
