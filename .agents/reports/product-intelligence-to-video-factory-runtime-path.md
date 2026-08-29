# Product Intelligence -> Video Factory Runtime Path Report

## Single-Machine Happy Path Status: PARTIALLY WIRED (One Link Missing)

### Producer: Product Intelligence
**File:** `hermes_personal/integrations/product_intelligence/client.py`::ProductIntelligenceClient

**Concrete producer methods:**
- `research()` → research dict with `owner: "product_intelligence"`, `schema: "product_research_report"`, workflow/job correlation fields
- `build_resource_pack()` → ResourcePackResult with `owner: "product_intelligence"`, schema: "product_resource_pack" (includes `scene_plan` steps)
- `lock_resource_pack()` → locked payload with `owner: "product_intelligence"`, schema: "product_resource_pack_locked", version, manifest_digest

**Producer traits:**
- Deterministic output (no external I/O for core flow)
- Injected via ProductVideoJobHandlers: `self.pi_client = pi_client or ProductIntelligenceClient()`
- Returns `JobSucceeded(artifact_ref=result)` on each success

### Durable Record/Topic: workflow_outbox

**Table schema (hermes_personal/storage/sqlite.py):**
```sql
CREATE TABLE workflow_outbox (
  outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
  workflow_id TEXT NOT NULL,
  message TEXT NOT NULL,  -- JSON envelope
  state TEXT NOT NULL DEFAULT 'pending',
  lease_token TEXT,  -- for claiming from worker
  lease_owner TEXT,
  lease_expires_at TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_attempt_at TEXT,
  last_error TEXT,
  created_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX workflow_outbox_claim_idx ON workflow_outbox(state, next_attempt_at, outbox_id);
```

**Producer → Durable Flow:**
- Producer calls: `JobSucceeded(artifact_ref=result, next_command={"command": "build_resource_pack", ...})`
- downstream calls `repository.commit_workflow(..., outbox_message=message_json)` (repository.py:115-119) → INSERT INTO `workflow_outbox`
- Message is JSON envelope (see envelope.py types)

### Handler/Runtime Composition: OutboxDispatcher

**File:** `hermes_personal/workflows/outbox_dispatcher.py`::OutboxDispatcher

**Interface signature:**
```python
def __init__(
    self,
    repository: OutboxRepository,
    delivery_fn: Callable[[str, str], None] | None = None,
    worker_id: str = ...,
    topic_handlers: Dict[str, Callable[[OutboxEnvelope], None]] | None = None,
) -> None
```

**Runtime loop (worker.py:61-67):**
```python
while not stop_event.is_set():
    dispatcher.reclaim_expired()
    dispatcher.process_batch(batch_size=10)
    stop_event.wait(poll_interval)
```

### What's Wired: HAPPY PATH UPSTREAM
✗ No producer directly calls `outbox_message` field in handlers
✗ No persistent flow recorded as durable Outbox messages for product_video.*
✗ No topic_handlers registered in `run_worker()` for `product_video.*` events (worker.py:100 "No topic_handlers registered for HP-007")

### What's Missing: FINAL CONSUMER LINK
```
ProductIntel.produce → commit_workflow(outbox_message) → workflow_outbox (pending)
                                                           ↓
                                                OutboxDispatcher.process_batch() (claims)
                                                           ↓
                                                No concrete topic-handlers registered
                                                           ↓
                                                **FAIL: unrecoverable quarentine after max_attempts (5)**
```

### Key Symbols
- `hermes_personal/product_video/handlers.py::ProductVideoJobHandlers.dispatch_registered_job()` (gate 4 to dispatcher/wiring entry)
- `hermes_personal/workflows/repository.py::commit_workflow(..., outbox_message)` (producer Gateway 4 record path)
- `hermes_personal/workflows/outbox_dispatcher.py::OutboxDispatcher` (consumer Gateway 5)
- `hermes_personal/workflows/outbox_repository.py::OutboxRepository` (storage)
- `hermes_personal/workflows/worker.py::run_worker()` (entry, uninitialized topic_handlers)
- `hermes_personal/workflows/envelope.py::OutboxEnvelope` (typed carrier for Router G5)

### File Paths
- Producer entry: `hermes_personal/product_video/handlers.py` (ProductVideoJobHandlers:*_job methods)
- Producer→record: `hermes_personal/workflows/repository.py:commit_workflow(..., outbox_message=...)`
- Durable sink: `hermes_personal/storage/sqlite.py:workflow_outbox` (CREATE TABLE)
- Consumer dispatcher: `hermes_personal/workflows/outbox_dispatcher.py`::OutboxDispatcher
- Consumer entry: `hermes_personal/workflows/worker.py:run_worker()`
- Consumer port: `hermes_personal/workflows/envelope.py::OutboxEnvelope`

### What's needed for happy path
Add `product_video.*` topic_handlers to OutboxDispatcher in `run_worker()`:

```python
topic_handlers = {
    "product_video.research": research_handler,
    "product_video.resource_pack": resource_pack_handler,
    "product_video.lock": lock_handler,
    "product_video.creative_brief": creative_brief_handler,
    "product_video.scene_plan": scene_plan_handler,
    "product_video.storyboard": storyboard_handler,
    "product_video.render": render_handler,
    "product_video.export": export_handler,
}
```

Each handler inspects envelope: `if env.message.get("command") == "product_video.intersection": ...`

### Root cause
**Missing bridge between Gate 4 (producer) and Gate 5 (consumer).**
- Producer emits durable Outbox/G4 record (called via `commit_workflow(outbox_message=...)`)
- Worker claims/holds pending entries forever (G5 await register) until concrete topic_handlers registered
- System quarentines unrecoverable after `max_attempts=5`

### Recommendation
Wire `product_video.*` handlers to OutboxDispatcher in single-machine scope (or remote scope same worker if single-machine). This is the smallest missing link.