# Phase 3 Daily Product Automation Design

Date: 2026-09-11
Status: Approved direction; implementation not started

## 1. Goal

Automate the handoff from the standalone Product-Intelligence repository into
the existing Hermes Product-to-Video workflow. Product-Intelligence runs on a
daily schedule, publishes an ordered pool of product candidates to a shared
filesystem path, and exits. Hermes discovers every complete batch, skips
products that already have or are currently producing a video, and starts the
next eligible products in rank order until the batch's target of three to five
new workflows is reached.

The design must remain small and understandable. It extends the existing daily
runner, workflow repository, outbox, runtime supervisor, and Product-to-Video
entry point. It does not restructure either repository.

## 2. Decisions

1. Product-Intelligence remains a standalone repository and remains the owner
   of market discovery, product identity, evidence, candidate ranking, and
   reference-image acquisition.
2. Hermes remains the owner of durable production state, duplicate prevention,
   workflow execution, HITL approvals, provider selection, rendering, and
   export.
3. A shared filesystem contract is the discovery transport. MCP remains
   available for the existing Product-Intelligence resource-pack operations,
   but the daily batch can be discovered and ingested while the MCP process is
   offline.
4. Product-Intelligence publishes an ordered pool, normally eight to ten
   candidates. Hermes claims only enough eligible products to meet a
   `target_count` between three and five.
5. Hermes never edits or moves a published source batch. It records consumption
   in its SQLite database and copies claimed inputs into a workflow-owned work
   directory.
6. The request file authorizes automatic discovery and workflow creation. No
   additional Daily Lineup approval is introduced. The existing Product Lock,
   Brief, Scene Plan, Storyboard, and Final approval gates remain mandatory.
7. Hermes starts a source-backed workflow at the existing Product Lock review
   point and does not repeat broad market research.
8. The automation uses polling and startup catch-up. It does not add a message
   broker, filesystem-watcher dependency, or new core model tool.

## 3. Non-goals

- Moving either Git repository into a new monorepo.
- Moving Product-Intelligence discovery code or its MCP server into Hermes.
- Replacing the existing Product-to-Video state machine or five approval gates.
- Automatically approving artifacts on behalf of the operator.
- Implementing Google Flow browser video generation.
- Building a dashboard for the queue in Phase 3.
- Introducing RabbitMQ, Redis, Kafka, a DLQ, or an external database.
- Rejecting a usable product because optional view classification or semantic
  image scoring is incomplete.

## 4. Physical layout

The operational data lives under a stable workspace root. The source
repositories may remain at their current locations.

```text
D:\work\TikTok\
├── data-product\
│   ├── request.yaml
│   ├── runs\
│   │   └── 2026-09-11\
│   │       └── pi-2026-09-11-01\
│   │           ├── manifest.json
│   │           ├── products\
│   │           │   └── jisulife-life-7-default\
│   │           │       ├── product.json
│   │           │       └── images\
│   │           │           ├── image-01.png
│   │           │           └── image-02.jpg
│   │           └── READY
│   └── work\
│       └── pv-pi-2026-09-11-01-a38f27a912bc\
│           └── input\
│               ├── product.json
│               └── images\
└── export\
    └── 2026-09-11\
        └── jisulife-life-7-default\
            └── pv-pi-2026-09-11-01-a38f27a912bc\
                ├── final.mp4
                └── metadata.json
```

Current repository paths do not need to change:

```text
D:\work\hermes-upstream-rearchitecture
D:\work\Personal\Product-Intelligence
```

The data and export roots are configured in each application. They are not
hard-coded and are not user-facing environment variables.

## 5. Minimal source changes

### Product-Intelligence

```text
product_scout/
├── daily_runner.py        # existing; read request and publish to configured root
└── daily_contract.py      # new; contract validation, digests, READY publication
```

The existing `scripts/daily_scout.py` and Windows Task Scheduler setup remain
the executable and scheduling surfaces. Discovery, media, and research modules
stay where they are.

### Hermes upstream

```text
hermes_personal/product_video/
├── handlers.py            # existing; add source-backed workflow entry point
└── daily_automation.py    # new; scan, validate, dedupe, claim, and start

hermes_personal/storage/sqlite.py   # extend schema with source-run ledger
hermes_personal/runtime/processes.py # register the small polling process
```

`daily_automation.py` is one bounded module in Phase 3. It may be split later
only if its responsibilities grow beyond the file contract and coordinator.

## 6. Configuration

### Shared request

`D:\work\TikTok\data-product\request.yaml` is the owner-editable source of
daily research requirements.

```yaml
schema: daily_product_request
version: 1
enabled: true
timezone: Asia/Bangkok
category: "Gia dụng & Tiện ích thông minh"
market: VN
platforms:
  - tiktok
price:
  currency: VND
  min: 200000
  max: 1500000
candidate_limit: 10
target_count: 3
minimum_images: 2
defaults:
  image_provider: visual_browser
  video_provider: vertex
```

Contract rules:

- `candidate_limit` is from 3 through 30.
- `target_count` is from 3 through 5 and cannot exceed `candidate_limit`.
- `minimum_images` defaults to 2 and cannot be lower than 1.
- The request file contains behavior only. Provider credentials stay in the
  applications' secret stores.

### Product-Intelligence config

```yaml
daily_scout:
  request_path: D:\work\TikTok\data-product\request.yaml
  publish_root: D:\work\TikTok\data-product\runs
```

### Hermes config

```yaml
personal:
  product_video:
    automation:
      enabled: true
      source_root: D:\work\TikTok\data-product\runs
      work_root: D:\work\TikTok\data-product\work
      export_root: D:\work\TikTok\export
      poll_interval_seconds: 60
      owner_user_id: local-owner
```

The runtime rejects an enabled automation with missing roots rather than
silently falling back to a repository-relative directory.

## 7. Published batch contract

### `manifest.json`

```json
{
  "schema": "daily_product_batch",
  "version": 1,
  "run_id": "pi-2026-09-11-01",
  "run_date": "2026-09-11",
  "published_at": "2026-09-11T07:12:04+07:00",
  "request_digest": "sha256:4be8...",
  "target_count": 3,
  "candidate_count": 10,
  "items": [
    {
      "product_key": "jisulife:life-7:default",
      "priority": 1,
      "product_path": "products/jisulife-life-7-default/product.json",
      "product_digest": "sha256:9c03..."
    }
  ]
}
```

Rules:

- `run_id` is immutable and unique for one published run.
- `priority` is a positive integer and unique within the run. Lower values are
  processed first.
- `candidate_count` equals the number of `items`.
- `product_path` is relative to the run directory.
- `product_digest` covers the exact bytes of `product.json`.
- An existing `run_id` published with different bytes is a conflict and is not
  ingested as a new version.

### `product.json`

```json
{
  "schema": "product_video_source",
  "version": 1,
  "product_key": "jisulife:life-7:default",
  "canonical_product_id": "jisulife-life-7",
  "variant_id": null,
  "name": "Quạt cầm tay mini Jisulife Life 7",
  "brand": "Jisulife",
  "model": "Life 7",
  "category": "Gia dụng & Tiện ích thông minh",
  "pdp_url": "https://example.invalid/product",
  "hot_reason": "Pin lớn, dễ trình diễn và phù hợp nội dung mùa nóng.",
  "key_features": [
    "pin 5000mAh",
    "5 cấp độ gió",
    "thiết kế gập"
  ],
  "keywords": [
    "Jisulife Life 7",
    "quạt cầm tay 5000mAh"
  ],
  "research": {
    "snapshot_id": "snap-2026-09-11-jisulife-life-7",
    "persistence_status": "saved",
    "evidence": [
      {
        "url": "https://example.invalid/source",
        "title": "Product specification",
        "claim_keys": ["battery_capacity", "speed_levels"]
      }
    ]
  },
  "images": [
    {
      "asset_id": "asset-c35a",
      "path": "images/image-01.png",
      "sha256": "f01b...",
      "width": 1000,
      "height": 1000,
      "view": "unknown",
      "match_score": 1.0
    }
  ],
  "providers": {
    "image": "visual_browser",
    "video": "vertex"
  }
}
```

`product_key` is the cross-run production identity. Product-Intelligence
constructs it from normalized brand, model, and variant. A marketplace listing
ID is not sufficient because the same product may appear in several listings.
If identity cannot be resolved without ambiguity, the item is omitted from the
published pool.

The `research` projection must reference a snapshot already persisted by
Product-Intelligence. The daily runner builds this projection from its existing
discovery evidence; Hermes does not conduct broad discovery again. The existing
Product-Intelligence MCP may later use `snapshot_id` to build and lock the
canonical Resource Pack after Product Lock approval.

## 8. Publication protocol

Product-Intelligence publishes one run as follows:

1. Parse and validate `request.yaml`.
2. Discover and rank up to `candidate_limit` products.
3. Resolve canonical identity and persist a research snapshot for each item
   that may be published.
4. Download and validate reference images.
5. Write the run into a new directory without a `READY` marker.
6. Close every file, calculate digests, and write `manifest.json` last among
   the payload files.
7. Re-read the manifest and referenced files through the same contract
   validator used by producer tests.
8. Atomically rename `READY.tmp` to `READY` in the run directory.

Hermes ignores every directory without `READY`. Product-Intelligence never
changes a run after `READY` exists. A retry with the same request and date may
reuse an already published byte-identical run or publish a new `run_id`; it may
not overwrite a completed run.

The `READY` file contains the SHA-256 digest of `manifest.json` followed by a
newline. An empty marker is invalid.

## 9. Hermes ingestion and selection

On process startup and every configured poll interval, Hermes:

1. Lists `source_root/<date>/<run_id>/READY` files in ascending date and
   `published_at` order.
2. Reads the manifest only after validating the `READY` digest.
3. Resolves every referenced path and verifies it remains beneath the run
   directory.
4. Inserts or confirms the source-run ledger entry.
5. Orders items by `priority`.
6. Evaluates each item until `target_count` workflows have been claimed or the
   candidate list is exhausted.
7. Copies a claimed item's `product.json` and images to
   `work_root/<workflow_id>/input`.
8. Starts the source-backed Product-to-Video workflow with deterministic IDs.

Selection decisions:

| Existing condition for `product_key` | Decision |
|---|---|
| No earlier production | Claim and start |
| Active or waiting workflow | Skip as `active_duplicate` |
| Completed workflow | Skip as `completed_duplicate` |
| Retryable workflow failure | Do not create; leave recovery to that workflow |
| Terminal workflow failure | Skip as `terminal_failure` |
| Invalid source item | Skip as `invalid_source` and continue |

Skipped candidates do not count toward `target_count`. A claimed workflow does
count even when it immediately waits at Product Lock; this prevents the scanner
from starting an unlimited number of workflows while earlier ones await human
review.

The default policy treats a completed product as permanently produced. A future
request schema version may add an explicit repeat campaign. Phase 3 does not
infer that a different date or listing URL authorizes another video.

## 10. Stable identity and idempotency

For an item:

```text
queue_id    = <run_id>:<product_key>
workflow_id = pv-<safe_run_id>-<first_12_hex(sha256(product_key))>
project_id  = proj-<workflow_id>
idempotency_key = daily-source:<queue_id>
```

All strings are normalized to the existing identifier constraints before use.
The original values remain in the workflow aggregate for audit.

The coordinator uses the same SQLite connection as `WorkflowRepository` and
commits the source claim, workflow aggregate, `WorkflowStarted` event, and first
outbox record in one transaction. A unique `queue_id` prevents a second claim.
The deterministic `workflow_id` provides a second guard during crash recovery.

## 11. Source-backed workflow start

A new entry point is added beside the existing
`start_product_video_workflow()`:

```python
def start_product_video_from_source(
    workflow_repository: WorkflowRepository,
    *,
    workflow_id: str,
    project_id: str,
    owner_user_id: str,
    source_run_id: str,
    source_product: dict[str, Any],
    source_digest: str,
    image_provider: str,
    video_provider: str,
    idempotency_key: str,
) -> str:
    ...
```

This entry point does not enqueue `product_video.research`. It creates the
workflow with the source research projection as `latest_artifact`, records the
provider bindings and source provenance in the aggregate, creates the normal
`AwaitingProductLock` approval request, and commits all records atomically.

The first approval shows product identity, features, evidence, and all source
images. Approving it follows the existing state transition into
`BUILDING_RESOURCE_PACK` and enqueues `product_video.resource_pack` with the
approved source research projection. The downstream Brief, Scene Plan,
Storyboard, Render, Final approval, and Export paths remain unchanged.

The source projection must contain a persisted Product-Intelligence
`snapshot_id`. Therefore, the existing configured Product-Intelligence adapter
can build the Resource Pack without another broad research call. If that MCP is
temporarily offline, the durable outbox retries the pack job; it does not create
a second workflow.

Moving the Product-Intelligence MCP implementation into Hermes is intentionally
outside this phase. The filesystem contract and `snapshot_id` boundary allow
that deployment choice to change later without changing the daily automation.

## 12. SQLite ledger

Two small tables are added to the existing Hermes Personal SQLite schema.

```sql
CREATE TABLE IF NOT EXISTS daily_product_run (
  run_id TEXT PRIMARY KEY,
  manifest_digest TEXT NOT NULL,
  source_path TEXT NOT NULL,
  run_date TEXT NOT NULL,
  target_count INTEGER NOT NULL CHECK(target_count BETWEEN 3 AND 5),
  status TEXT NOT NULL CHECK(status IN ('ingested', 'partial', 'completed', 'rejected')),
  last_error TEXT,
  imported_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_product_item (
  queue_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES daily_product_run(run_id) ON DELETE CASCADE,
  product_key TEXT NOT NULL,
  priority INTEGER NOT NULL,
  product_digest TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('new', 'claimed', 'skipped_duplicate', 'skipped_invalid')),
  workflow_id TEXT,
  skip_reason TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(run_id, product_key),
  UNIQUE(run_id, priority)
);

CREATE INDEX IF NOT EXISTS daily_product_item_identity_idx
  ON daily_product_item(product_key, status);
```

The item ledger owns only ingestion decisions. After an item is `claimed`, the
canonical workflow state is read from the existing `workflow` aggregate. The
automation does not copy the Product-to-Video state machine into these tables.

Run status is derived as follows:

- `ingested`: manifest accepted and items recorded, no claim pass completed;
- `partial`: fewer than `target_count` items are claimed and unexamined items
  remain or recoverable source errors exist;
- `completed`: `target_count` items are claimed, or all candidates have a final
  claim/skip decision;
- `rejected`: manifest-level validation failed and no item was ingested.

## 13. Runtime behavior

Product-Intelligence is started daily by the existing Windows Task Scheduler
script. A failed daily run exits non-zero and does not publish `READY`.

Hermes registers a lightweight `daily_product_automation` process with its
existing supervisor only when the feature is enabled. The process performs an
immediate scan, then polls every 60 seconds by default. It has no model loop and
does not add a tool schema. If Hermes is offline during publication, the next
startup scan catches up from the oldest unprocessed run.

Only one automation coordinator may claim work for a Hermes profile at a time.
It uses a SQLite transaction rather than a filesystem lock. Existing workflow
outbox leases continue to control downstream job execution.

The coordinator starts eligible workflows in priority order during one claim
pass. It does not wait for rank 1 to finish before starting rank 2. This allows
three to five workflows to reach their human review gates promptly. Paid video
jobs and Visual Browser work retain their own bounded or serialized provider
capacity rules.

## 14. Input admission

A product is eligible when:

- `product_key`, name, canonical product identity, research snapshot, features,
  evidence, and provider bindings are present;
- at least the request's `minimum_images` files exist and can be decoded;
- every accepted image digest matches;
- at least one image has acceptable product identity confidence;
- no image is known to show a conflicting model or variant.

The following conditions produce warnings and ranking metadata but do not block
an otherwise usable item:

- `view` is `unknown`;
- fewer than three images are available when the configured minimum is two;
- optional price fields are absent;
- visual or semantic quality is adequate but not ideal.

A bad item is marked `skipped_invalid`; the coordinator continues to the next
ranked candidate. A bad item never rejects the entire valid batch.

## 15. Error handling and recovery

| Failure | Required behavior |
|---|---|
| No `READY` marker | Ignore as an incomplete publication |
| `READY` digest mismatch | Reject run; do not ingest items |
| Unsupported schema version | Reject run with explicit version error |
| Same `run_id`, different digest | Reject as immutable-run conflict |
| One invalid product | Skip item and continue filling target |
| Source path escapes run directory | Skip item and log security error |
| Copy interrupted | Remove only the incomplete workflow input directory and retry the same claim |
| Crash during workflow creation | SQLite rollback; deterministic IDs make the next scan safe |
| MCP unavailable after approval | Existing outbox retry; no second workflow |
| Export path unavailable | Existing workflow remains non-completed and retries/reports normally |

Retryable infrastructure failures do not become `skipped_invalid`. They keep the
run `partial` and are retried on a later scan. Contract or identity failures are
terminal for that source item.

## 16. Security and integrity

- Resolve every relative source path and verify it is beneath the canonical run
  directory before reading.
- Reject symlinks and junctions inside a published product payload.
- Verify manifest, product, and image digests before workflow creation.
- Decode images with bounded dimensions and file size using the existing media
  validation path.
- Treat all product text as untrusted source data. It may populate workflow
  artifacts but cannot alter system prompts, tool configuration, paths, or
  provider credentials.
- Copy claimed inputs into a workflow-owned directory so later source retention
  or cleanup cannot change an active workflow.
- Keep credentials out of `request.yaml`, manifests, logs, and export metadata.

## 17. Export contract

The existing export job writes the approved final artifact beneath the configured
export root:

```text
<export_root>/<run_date>/<safe_product_key>/<workflow_id>/final.mp4
<export_root>/<run_date>/<safe_product_key>/<workflow_id>/metadata.json
```

`metadata.json` contains `workflow_id`, `project_id`, `source_run_id`,
`product_key`, source and final artifact digests, provider names, approval
receipt references, and completion time. It contains no credentials or copied
browser session data.

## 18. Observability

Use structured logs from the existing Hermes logging setup. One completed scan
emits a compact summary:

```text
run_id=pi-2026-09-11-01 candidates=10 claimed=3 duplicates=2 invalid=1 remaining=4
```

Log one reason for every skipped or rejected item. Repeated scans of an unchanged
completed run remain quiet. Operational status is queryable from SQLite; Phase 3
does not add a model tool or dashboard.

## 19. Test strategy

### Product-Intelligence focused tests

- Request validation accepts target counts three through five and rejects an
  invalid target/candidate relationship.
- Publication writes `READY` only after every referenced file exists.
- Replaying a byte-identical run is idempotent.
- Publishing the same `run_id` with different content is rejected.
- The manifest contains unique priority and stable product keys.
- A published research snapshot can be retrieved by the existing MCP service.

### Hermes focused tests

- Directories without `READY` are ignored.
- Manifest digest, path containment, product digest, and image digests are
  enforced.
- An invalid item does not block later candidates.
- Completed and active product identities are skipped.
- The coordinator claims in priority order until `target_count` is reached.
- A replay creates no duplicate source items, workflows, events, or outbox rows.
- A crash between source parsing and transaction commit leaves no partial claim.
- A source-backed workflow has no `product_video.research` outbox message and
  enters `AwaitingProductLock` with the correct source artifact.
- Approval of that artifact continues through the existing Resource Pack path.
- Startup catch-up processes a batch published while Hermes was offline.

### End-to-end acceptance test

Using temporary data and Hermes homes:

1. Publish ten products: two completed duplicates, one invalid item, and seven
   valid new items, with `target_count=3`.
2. Start the Hermes automation process.
3. Assert that exactly the first three valid unseen products are claimed in
   priority order.
4. Assert that exactly three workflows and three first approval requests exist.
5. Restart the process and assert that all counts remain unchanged.
6. Approve one Product Lock and assert that it uses the persisted snapshot and
   enqueues Resource Pack construction without a broad research call.

Focused Windows verification commands:

```powershell
uv run pytest tests/hermes_personal/product_video -q
uv run pytest tests/hermes_personal/runtime -q
uv run ruff check hermes_personal tests/hermes_personal
```

Product-Intelligence verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_daily_scout.py -q
```

## 20. Acceptance criteria

Phase 3 is complete when all of the following are true:

1. The owner can change daily requirements in one `request.yaml` file.
2. Windows Task Scheduler can start Product-Intelligence without starting
   Hermes or the MCP server.
3. A successful daily run publishes an immutable, digest-verified batch and
   writes `READY` last.
4. Hermes automatically discovers batches on startup and during normal runtime.
5. Hermes skips active and completed product identities and continues down the
   ordered pool.
6. Hermes starts exactly enough eligible workflows to meet `target_count`, up
   to the available candidate count.
7. Source-backed workflows do not repeat broad Product-Intelligence research.
8. Every new workflow reaches the existing `AwaitingProductLock` gate with
   identity, evidence, and images visible for review.
9. Restarting either process does not duplicate a run, source item, workflow,
   event, paid request, or exported video.
10. One malformed product does not stop other valid products in the batch.
11. Optional image metadata does not become an unnecessary production blocker.
12. Completed videos and metadata are written beneath the configured export
    root.

## 21. Delivery boundary

Phase 3 delivers scheduled discovery, filesystem handoff, durable ingestion,
duplicate-aware ordered claiming, and automatic source-backed workflow creation.
It reuses the current Product-to-Video approvals and downstream jobs.

Provider adapter improvements, browser-profile serialization, automatic approval
policies, richer portfolio scoring, repeat campaigns, and a queue dashboard are
separate follow-up phases. Their absence does not prevent Phase 3 from starting
the correct daily workflows safely and predictably.
