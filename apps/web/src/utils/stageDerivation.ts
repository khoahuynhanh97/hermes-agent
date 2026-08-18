import { CANONICAL_STAGES, StageKey, StageState, VideoFactoryProject } from '../types/videoFactory'

export function getStageDependency(stageKey: StageKey): { dependsOn: StageKey; label: string; reason: string } | null {
  switch (stageKey) {
    case 'brief':
      return {
        dependsOn: 'resources',
        label: 'Product Resources',
        reason: 'Creative Brief requires locked product resources to define brand and messaging constraints.',
      }
    case 'scenes':
      return {
        dependsOn: 'brief',
        label: 'Creative Brief',
        reason: 'Scene Plan requires an approved Creative Brief to structure 30s narrative pacing.',
      }
    case 'storyboard':
      return {
        dependsOn: 'scenes',
        label: 'Scene Plan',
        reason: 'Storyboard Keyframes require an approved Scene Plan with defined duration and visual state for each scene.',
      }
    case 'generation':
      return {
        dependsOn: 'storyboard',
        label: 'Storyboard Keyframes',
        reason: 'Scene Video Generation requires storyboard keyframes to maintain visual consistency.',
      }
    case 'timeline':
      return {
        dependsOn: 'generation',
        label: 'Scene Videos',
        reason: 'Timeline Assembly requires generated scene video clips to render a draft video.',
      }
    case 'export':
      return {
        dependsOn: 'timeline',
        label: 'Draft Timeline',
        reason: 'Final Export requires a rendered draft video before master publishing.',
      }
    default:
      return null
  }
}

export function isStageCompleted(stageKey: StageKey, project: VideoFactoryProject | null): boolean {
  if (!project) return false

  switch (stageKey) {
    case 'resources':
      return Boolean(
        project.resource_pack &&
        (project.resource_pack.id || (project.resource_pack.product_references && project.resource_pack.product_references.length > 0))
      )

    case 'brief':
      return project.brief_approval === 'approved' && Boolean(project.creative_brief?.objective)

    case 'scenes':
      return (
        project.scene_plan_approval === 'approved' &&
        Boolean(project.scene_plan?.scenes && project.scene_plan.scenes.length > 0)
      )

    case 'storyboard':
      const frames = project.storyboard?.frames || []
      return frames.length > 0 && frames.every((f) => f.generation_status === 'completed' || Boolean(f.generated_asset_id))

    case 'generation':
      const scenes = project.generated_scenes || []
      return scenes.length > 0 && scenes.every((s) => s.generation_status === 'completed' || Boolean(s.generated_asset_id))

    case 'timeline':
      return Boolean(project.draft_video_asset_id || (project.timeline && project.timeline.clips?.length > 0))

    case 'export':
      return Boolean(project.final_video_asset_id || project.status === 'ready_to_publish')

    default:
      return false
  }
}

export function isStageBlocked(stageKey: StageKey, project: VideoFactoryProject | null): boolean {
  if (!project) return stageKey !== 'resources'

  const dep = getStageDependency(stageKey)
  if (!dep) return false

  return !isStageCompleted(dep.dependsOn, project)
}

export function deriveStageState(
  stageKey: StageKey,
  project: VideoFactoryProject | null,
  currentViewStage?: StageKey,
  activeJobTask?: string
): StageState {
  if (!project) return stageKey === 'resources' ? 'active' : 'not_started'

  if (isStageCompleted(stageKey, project)) {
    return 'completed'
  }

  if (isStageBlocked(stageKey, project)) {
    return 'blocked'
  }

  if (activeJobTask && activeJobTask.toLowerCase().includes(stageKey)) {
    return 'running'
  }

  if (currentViewStage === stageKey) {
    return 'active'
  }

  return 'not_started'
}

export function deriveActiveStage(project: VideoFactoryProject | null): StageKey {
  if (!project) return 'resources'

  for (const meta of CANONICAL_STAGES) {
    if (!isStageCompleted(meta.key, project)) {
      return meta.key
    }
  }

  return 'export'
}

export function derivePipelineProgress(project: VideoFactoryProject | null): number {
  if (!project) return 0
  let completedCount = 0
  for (const meta of CANONICAL_STAGES) {
    if (isStageCompleted(meta.key, project)) {
      completedCount++
    }
  }
  return Math.round((completedCount / CANONICAL_STAGES.length) * 100)
}

export function getNextStage(current: StageKey): StageKey | null {
  const idx = CANONICAL_STAGES.findIndex((s) => s.key === current)
  if (idx >= 0 && idx < CANONICAL_STAGES.length - 1) {
    return CANONICAL_STAGES[idx + 1].key
  }
  return null
}

export function getPrevStage(current: StageKey): StageKey | null {
  const idx = CANONICAL_STAGES.findIndex((s) => s.key === current)
  if (idx > 0) {
    return CANONICAL_STAGES[idx - 1].key
  }
  return null
}
