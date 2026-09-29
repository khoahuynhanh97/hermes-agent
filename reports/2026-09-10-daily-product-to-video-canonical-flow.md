# Daily Product-to-Video Canonical Flow

Date: 2026-09-10

## Decision

Product-Intelligence owns daily market discovery, candidate media readiness,
product identity, evidence, and source media. Hermes upstream owns daily production
selection, human approvals, workflow fan-out, creative planning, generation,
rendering, export, and delivery.

Hermes must not repeat broad market discovery. It should consume a versioned,
approved `DailyProductionManifest`, then create one durable Product-to-Video
workflow for every selected item.

## Current reality

`D:/work/Personal/Product-Intelligence/data/daily_runs/2026-09-10/products.json`
contains ten products. All ten have two readable local image files. Minimum short
edge ranges from 451 to 1024 pixels. This is sufficient for a practical first
keyframe-generation pass.

The current `products.json` is a discovery/report projection, not yet a durable
production contract. It does not contain:

- selection and approval state;
- immutable daily manifest identity and digest;
- canonical research snapshot and ready-to-lock Resource Pack references;
- structured content direction;
- image and video provider bindings;
- workflow/project/idempotency identifiers;
- per-item production status.

The current Hermes entry point accepts only `product_name`, `keywords`,
`pdp_url`, `project_id`, and ownership. It therefore starts another research
job. Directly importing `products.json` through that entry point would duplicate
work and would not bind the selected images to the workflow.

## Ownership boundaries

### Product-Intelligence

- Run daily discovery from `request.txt`.
- Resolve category, price range, market, and candidate target.
- Collect a larger candidate pool.
- Resolve canonical product and variant identity.
- Persist lightweight source evidence for the candidate batch.
- Download, validate, deduplicate, and classify reference images.
- After lineup selection, prepare immutable research snapshots and Resource Pack
  drafts only for the selected three to five products.
- Expose the daily batch and product preparation results through MCP or a local
  adapter.

### Hermes upstream

- Ingest one daily batch without rediscovering the market.
- Apply production-admission checks.
- Rank by production value and portfolio diversity.
- Propose three to five items and a content direction for each.
- Request operator approval for the daily lineup.
- Freeze the approved Daily Production Manifest.
- Fan out one durable workflow per selected product.
- Run Product Lock, Brief, Scene Plan, Storyboard, and Final Video approvals.
- Select and persist image/video providers independently.
- Track budget, paid-job checkpoints, retries, exports, and delivery.

### Generation providers

- Vertex/API image provider: generate keyframes from prompt and references.
- Visual Browser MCP: use Playwright, the persistent Chrome profile, and Google
  Flow to upload references, generate/download keyframes, and return evidence.
- Vertex AI Veo: submit and poll video generation through the API.
- Google Flow browser video: future provider using the same canonical render
  contract; the current Visual Browser MCP remains image-only.

## Minimum production admission

Keep this practical and avoid an overly strict QC gate. A product can enter the
daily slate when:

1. It has one unambiguous product identity, or the operator explicitly selects
   the intended variant.
2. At least two reference images exist and can be decoded; three are preferred.
3. At least one image has acceptable identity confidence and there is no known
   conflicting model identity.
4. The source and usage policy permit the configured use as a generation
   reference.
5. Product name, useful features, hot reason, and at least one evidence/source
   reference are present.
6. The product has not already been scheduled within the suppression window.

Missing optional metadata such as perfect view classification should lower the
rank or request a review, not automatically block the whole daily run.

## Daily selection policy

The planner should select three to five products from the admitted pool using:

- trend and commercial relevance;
- content potential and demonstrability;
- media readiness;
- evidence quality;
- category and brand diversity;
- recent-production suppression;
- available daily budget and provider capacity.

For each selected product it proposes a structured `ContentDirection`:

- angle and one-sentence promise;
- hook;
- target audience;
- platform and aspect ratio;
- target duration;
- key features and allowed claims;
- must-show product details;
- CTA;
- preferred image provider and video provider.

The operator can approve, reject, reorder, or edit the direction. Approval
freezes the manifest version used for workflow fan-out.

## Canonical bridge contract

```json
{
  "schema": "daily_production_manifest",
  "version": 1,
  "manifest_id": "daily-2026-09-10-v1",
  "source_run_date": "2026-09-10",
  "source_run_ref": "product-intelligence:2026-09-10",
  "owner_user_id": "owner-1",
  "status": "approved",
  "approved_at": "2026-09-10T08:00:00+07:00",
  "digest": "sha256:...",
  "items": [
    {
      "selection_id": "daily-2026-09-10:prod_01",
      "rank": 1,
      "canonical_product_id": "...",
      "variant_id": null,
      "product_name": "Quạt cầm tay mini Jisulife Life 7",
      "brand": "Jisulife",
      "model": "Life 7",
      "research_snapshot_id": "snapshot_...",
      "resource_pack_id": "pack_...",
      "resource_pack_status": "ready_to_lock",
      "reference_assets": [
        {
          "asset_id": "sha256...",
          "path": "D:/.../image_1.png",
          "digest": "sha256:...",
          "usage_policy": "reference_only"
        }
      ],
      "content_direction": {
        "angle": "Portable cooling for commuting",
        "hook": "Nắng nóng nhưng chiếc quạt này dùng gần cả ngày",
        "audience": "người đi làm và sinh viên",
        "platform": "tiktok",
        "aspect_ratio": "9:16",
        "target_duration_seconds": 20,
        "must_show": ["màn hình pin", "thiết kế gập", "cổng Type-C"],
        "allowed_claims": ["pin 5000mAh", "5 cấp độ gió"],
        "cta": "Xem sản phẩm"
      },
      "providers": {
        "image": "visual_browser",
        "video": "vertex"
      },
      "workflow_id": "pv-2026-09-10-prod-01",
      "project_id": "proj-pv-2026-09-10-prod-01",
      "idempotency_key": "daily-2026-09-10-v1:prod_01"
    }
  ]
}
```

## Canonical runtime sequence

1. Product-Intelligence completes the dated daily run and publishes a lightweight
   candidate batch with usable reference images.
2. Hermes ingests that batch once using `source_run_ref` as the deduplication
   key.
3. Hermes validates production readiness and generates the three-to-five-item
   content slate.
4. The operator approves or edits the slate (`Daily Lineup` gate).
5. For only the approved items, Hermes asks Product-Intelligence to create the
   immutable research snapshot and ready-to-lock Resource Pack draft. A failed
   preparation returns the item for replacement instead of blocking the other
   approved items.
6. Hermes persists an immutable Daily Production Manifest containing those
   prepared references.
7. The outbox fans out one workflow command per manifest item. Replaying the
   fan-out cannot create a second workflow because `selection_id` and
   `idempotency_key` are stable.
8. Each workflow binds the existing Product-Intelligence snapshot/Resource Pack
   draft. It does not run broad discovery again.
9. Product Lock approval calls Product-Intelligence to lock the exact product,
   variant, claims, and media list. The returned immutable lock ref becomes the
   root of the video artifact chain.
10. Hermes creates and approves the creative brief and scene plan.
11. Each storyboard frame is converted to a canonical `KeyframeRequest` and sent
    to the project's bound image provider. Provider results normalize to the
    same `KeyframeArtifact` contract.
12. Storyboard approval freezes the frame artifacts.
13. A canonical `VideoRenderRequest` is sent to the bound video provider. Hermes
    reserves budget before submit, persists the provider operation ID
    immediately, and polls/resumes without resubmitting.
14. Final approval authorizes export. The MP4 and metadata are saved and
    delivered.
15. Per-item outcome updates the Daily Production Manifest projection and feeds
    production history into the next day's suppression/diversity policy.

## Required bridge changes

1. Product-Intelligence should expose the daily batch through a stable MCP tool
   such as `get_daily_products(date)` and a preparation tool such as
   `prepare_product_for_video(product_id)`; a local file adapter may be used for
   the first single-machine version.
2. Add a Hermes `DailyProductIngestService` that validates and snapshots the
   source batch without implementing discovery logic.
3. Add `DailyProductionManifest` persistence and the Daily Lineup approval gate.
4. Add an idempotent fan-out service that starts one workflow per approved item.
5. Extend the Product-to-Video start contract to accept existing
   `research_snapshot_id`, `resource_pack_id`, reference asset refs,
   `content_direction`, and provider bindings. When these are valid, skip the
   duplicate research stage.
6. Add a canonical keyframe generation port and adapters for Vertex/API image
   generation and Visual Browser MCP.
7. Persist `image_provider`, `video_provider`, external job IDs, and artifact
   digests in each workflow aggregate.
8. Serialize Visual Browser generation per Chrome profile. Keep Vertex/API work
   under bounded concurrency and the existing budget controls.

## Implementation status reviewed on 2026-09-11

The existing single-product Product-to-Video workflow is healthy: its focused
suite passes 125 tests. Product-Intelligence daily scouting also passes its five
focused tests. The following bridge work is still absent from runtime code and
is required for the intended daily end-to-end flow:

1. Stable daily-batch read and selected-product preparation tools in
   Product-Intelligence.
2. Hermes daily ingest, lineup approval, immutable manifest persistence, and
   idempotent fan-out.
3. A Product-to-Video start path that binds prepared snapshot/pack/assets and
   skips duplicate research.
4. A canonical keyframe port with Vertex/API and Visual Browser MCP adapters.
5. Durable per-workflow image/video provider bindings plus browser-profile
   serialization.

Browser-based video generation is not required for the first working version;
Visual Browser MCP currently supports image generation while Vertex/Veo handles
video. Richer view classification, semantic image scoring, and automatic lineup
approval are follow-up improvements and must not block the first daily flow.

## Capacity rule

Three to five daily workflows do not need to run all paid/browser work in
parallel. Metadata planning can run concurrently. Visual Browser MCP should
serialize generation per Chrome profile. Vertex jobs can use bounded parallelism
subject to budget and quota. This keeps daily throughput predictable without
creating profile-lock conflicts or duplicate paid submissions.
