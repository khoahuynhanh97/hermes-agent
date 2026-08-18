import { describe, it } from 'node:test'
import assert from 'node:assert'
import {
  isStageCompleted,
  isStageBlocked,
  deriveActiveStage,
  derivePipelineProgress,
  deriveStageState,
} from './stageDerivation.ts'
import { VideoFactoryProject } from '../types/videoFactory.ts'

describe('Stage Derivation Logic', () => {
  const emptyProject: VideoFactoryProject = {
    id: 'test-empty',
    owner_user_id: 'user',
    status: 'draft',
  }

  const completedProject: VideoFactoryProject = {
    id: 'test-completed',
    owner_user_id: 'user',
    status: 'ready_to_publish',
    resource_pack: {
      id: 'lock-1',
      owner_user_id: 'user',
      product_references: [{ asset_id: 'asset-1' }],
      primary_product_asset_id: 'asset-1',
      product_identity_description: 'Test Product',
      locked_at: '2026-08-15',
      version: 1,
    },
    creative_brief: {
      objective: 'Promote sound quality',
      target_audience: 'Commuters',
      core_message: 'Best in class ANC',
      content_blocks: ['Hook', 'Use case', 'Highlights', 'CTA'],
    },
    brief_approval: 'approved',
    scene_plan: {
      scenes: [
        {
          scene_id: 'scene_1',
          order: 1,
          title: 'Hook',
          purpose: 'Capture attention',
          content: 'Intro',
          visual_style: 'Studio',
          duration_seconds: 6,
          setting: 'Studio',
          camera_movement: 'Push in',
        },
      ],
    },
    scene_plan_approval: 'approved',
    storyboard: {
      frames: [
        {
          frame_id: 'frame_1',
          scene_id: 'scene_1',
          order: 1,
          label: 'Hook',
          purpose: 'Hook',
          visual_state: 'Reveal',
          subject_action: 'Reveal',
          product_state: 'Reveal',
          context: 'Studio',
          camera_intention: 'Push in',
          required_resource_ids: ['asset-1'],
          prompt: {
            positive_prompt: 'Prompt',
            negative_constraints: 'No text',
            product_identity_constraints: 'Test Product',
          },
          generation_status: 'completed',
          generated_asset_id: 'gen-frame-1',
          version: 1,
        },
      ],
    },
    generated_scenes: [
      {
        scene_id: 'scene_1',
        video_prompt: {
          scene_id: 'scene_1',
          duration_seconds: 6,
          start_visual_state: 'Start',
          end_visual_state: 'End',
          subject_action: 'Action',
          product_action: 'Action',
          camera_movement: 'Push in',
          camera_framing: '9:16',
          environment_motion: 'Motion',
          identity_constraints: 'Test',
          reference_frame_ids: ['frame_1'],
          dialogue_or_vo: '',
          negative_constraints: '',
          provider_options: {},
        },
        generation_status: 'completed',
        generated_asset_id: 'gen-scene-1',
        version: 1,
      },
    ],
    draft_video_asset_id: 'draft-video-1',
    final_video_asset_id: 'final-video-1',
  }

  it('correctly derives stage completion for empty and full projects', () => {
    assert.strictEqual(isStageCompleted('resources', emptyProject), false)
    assert.strictEqual(isStageBlocked('brief', emptyProject), true)
    assert.strictEqual(deriveActiveStage(emptyProject), 'resources')
    assert.strictEqual(derivePipelineProgress(emptyProject), 0)

    assert.strictEqual(isStageCompleted('resources', completedProject), true)
    assert.strictEqual(isStageCompleted('brief', completedProject), true)
    assert.strictEqual(isStageCompleted('scenes', completedProject), true)
    assert.strictEqual(isStageCompleted('storyboard', completedProject), true)
    assert.strictEqual(isStageCompleted('generation', completedProject), true)
    assert.strictEqual(isStageCompleted('timeline', completedProject), true)
    assert.strictEqual(isStageCompleted('export', completedProject), true)
    assert.strictEqual(derivePipelineProgress(completedProject), 100)
  })

  it('correctly handles stage state transitions', () => {
    assert.strictEqual(deriveStageState('resources', emptyProject, 'resources'), 'active')
    assert.strictEqual(deriveStageState('brief', emptyProject), 'blocked')
    assert.strictEqual(deriveStageState('export', completedProject), 'completed')
  })
})
