---
name: product-generation-prompt
description: Use when writing image or video generation prompts for a real product whose visual identity must remain faithful to locked references.
---

# Product Generation Prompt

Compile prompts from approved creative intent and the current durable product
identity. The lock is a constraint source, not creative prose.

## Preconditions

- Retrieve the current Resource Pack and locked identity.
- Refuse prompt finalization if identity is unlocked, provisional, conflicted,
  or belongs to another owner/project.
- Use canonical original product references in every identity-critical provider
  request. A generated frame is never the sole product reference.

## Prompt Contract

Build each prompt in this order:

1. Scene objective and action from the approved Scene Plan.
2. Product identity invariants, written as atomic visual constraints.
3. Required product state and visible components for this shot.
4. Composition, camera, lighting, environment, and motion.
5. Negative constraints derived from the lock and prior QC failures.
6. Canonical `reference_asset_ids`, aspect ratio, duration, and provider options.

Do not add an identity detail absent from the lock. Do not convert unknown details
into positive or negative constraints. Keep marketing claims separate from visual
identity. Prefer overlays during composition instead of asking a generator to
render exact advertising text.

## Continuity

- Reuse the same lock version across all frames and scenes in one approved batch.
- Preserve component count, topology, color placement, logo placement, and
  defining relationships whenever they are visible.
- Adapt constraints to the camera view; do not demand invisible details.
- A change to the identity lock invalidates prompts generated from the old lock.

## Paid Calls

Present the complete batch, model, reference set, and estimated call count. Stop
for explicit approval before submission. Never auto-retry or regenerate a paid
call after provider or QC failure.
