# Architectural Specification: Playwright-First Browser Flow for Hermes Personal Product Video

**Status:** Proposed / Draft  
**Author:** DeepMind Antigravity / Hermes Personal Team  
**Date:** 2026-09-19  
**Target Superpower:** Product Video Production Integrity & Grounded Evidence Capture  
**Scope:** Edge Browser Navigation & Source Ingestion with Strict Vertex AI Preservation  

---

## 1. Executive Summary & Intent

Hermes Personal requires high-fidelity, grounded product research and source media capture to feed the Product-to-Video pipeline. Currently, source research relies on external Product Intelligence MCP tools or static PDP URLs without an integrated, deterministic browser execution contract.

This specification designs a **Playwright-First Browser Flow** for Hermes Personal Product Video with the following inviolable principles:
1. **Playwright at the Edge**: Playwright operates as an edge adapter via MCP / tool ports to perform web navigation, source discovery, DOM extraction, and binary media ingestion.
2. **Untouched Vertex AI Pipeline**: Vertex AI Gemini (creative direction, script generation, vision evaluation, Image/Keyframe/Video QC) and Vertex AI Veo (video generation) remain 100% authoritative and unchanged. Playwright never replaces Vertex AI and never interacts with Vertex Console.
3. **Single Canonical Orchestrator**: `HermesTurnService` and the `ProductVideoWorkflowHandler` state machine remain the sole general-purpose brain and workflow engine. No secondary agent or shadow pipeline is introduced.
4. **Durable SQLite State**: All capture requests, raw page metadata, and ingested evidence artifacts are persisted in SQLite before advancing to creative synthesis.
5. **Zero Trust & Containment**: Content retrieved from the web is treated strictly as untrusted data, never as system instructions. Downloaded assets are bounded by workspace containment.

---

## 2. Current-State Trace

```
[CLI / Gateway / Telegram Ingress]
            │
            ▼
[HermesTurnService] ──> [ProductVideoWorkflowHandler]
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
   [Step 1: Product Research]    [Step 2: Resource Pack]
   MCP ProductIntelligence       Media manifest + claims
   (No native browser engine)    (In-memory / static URLs)
               │                             │
               └──────────────┬──────────────┘
                              ▼
               [Gate 1: Product Lock (HITL)]
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
   [Step 3: Creative Brief]      [Step 4: Scene Plan]
   Vertex AI Gemini              Vertex AI Gemini
               │                             │
               └──────────────┬──────────────┘
                              ▼
               [Step 5: Storyboard Keyframes]
               Vertex AI Gemini (Prompt + Reference Assets)
                              │
                              ▼
               [Gate 4: Storyboard Approval (HITL)]
                              │
                              ▼
               [Step 6: Video Render via Veo]
               VertexVideoProvider (predictLongRunning REST)
               (scene_renderer.py -> video_factory/server.py)
                              │
                              ▼
               [Step 7: Video QC & Gate 5: Final Approval]
               ProductVideoQCService (Gemini Vision Evaluation)
                              │
                              ▼
               [Step 8: Export Packaging]
               video_factory/server.py (H.264/AAC MP4)
```

### Current Data & State Storage Locations:
- **Workflow State & Outbox**: `hermes_personal.storage.sqlite` (`workflow`, `workflow_outbox`, `workflow_event`).
- **Research Results & Resource Pack**: `latest_artifact` on workflow aggregate + Video Factory SQLite repository.
- **Render Operations & Veo Checkpoints**: `video_factory_scene_operation`, `video_factory_render_batch` tables in `video_factory.sqlite` storing `provider_operation_id`, `request_digest`, and `output_sha256`.
- **Budget Reservations**: `budget_reservations` table (scope_id = `project_id`, service = `video_factory`, `gemini_flash`).
- **QC Reports & Lineage**: `product_video_qc_reports` table storing the canonical 6-tuple lineage (`owner_user_id`, `project_id`, `workflow_id`, `artifact_id`, `artifact_version`, `artifact_digest`).

---

## 3. Target Architecture: Playwright-First Edge Integration

Playwright is inserted cleanly at Step 1 (Source Discovery & Ingestion) while preserving the remainder of the pipeline.

```
                     ┌─────────────────────────────────────────────────────────┐
                     │               HermesTurnService (Canonical)             │
                     │          Workflow Engine + Outbox Dispatcher            │
                     └────────────────────────────┬────────────────────────────┘
                                                  │
                  ┌───────────────────────────────┴───────────────────────────────┐
                  ▼                                                               ▼
  ┌───────────────────────────────┐                               ┌───────────────────────────────┐
  │   Playwright Edge Adapter     │                               │      Vertex AI Pipeline       │
  │   (Browser Capture Service)   │                               │       (STRICTLY PRESERVED)    │
  ├───────────────────────────────┤                               ├───────────────────────────────┤
  │ • Headless Chromium Context   │                               │ • VertexVideoProvider (Veo)   │
  │ • PDP Navigation & Rendering  │                               │ • Gemini Multimodal Vision    │
  │ • Screenshot & DOM Snapshot   │                               │ • Scene Keyframe Generation   │
  │ • Binary Media Download       │                               │ • Image / Keyframe / Video QC │
  │ • Workspace Ingestion & Hash  │                               │ • Creative Brief & Scripts    │
  └───────────────┬───────────────┘                               └───────────────▲───────────────┘
                  │                                                               │
                  │ Ingested Evidence Artifacts (SHA256)                          │ Verified References
                  ▼                                                               │
  ┌───────────────────────────────────────────────────────────────────────────────┴───────────────┐
  │                           SQLite Durable Persistence Layer                                    │
  │   • browser_capture_records      • video_factory_scene_operation     • product_video_qc_reports│
  │   • workflow / workflow_outbox   • video_factory_render_batch        • budget_reservations    │
  └───────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Responsibility Matrix

| Component | Responsibility | Boundary / Prohibitions |
|---|---|---|
| **Playwright Edge Adapter** | Navigates URLs, awaits selectors, captures full-page/element screenshots, extracts DOM/text, downloads high-res images/videos, hashes files. | **PROHIBITED** from calling Vertex APIs, bypassing HITL gates, persisting cookies/credentials, or interpreting web content as system commands. |
| **Workflow / Outbox Engine** | Orchestrates state transitions, dispatches jobs, maintains replay idempotency, journals domain events. | Channel-neutral; no transport-specific brain logic. |
| **Product Research Module** | Parses raw capture data into canonical product dossier (brand, model, selling points, claims, evidence refs). | Operates purely on grounded ingested artifacts. |
| **Vertex Gemini** | Generates creative briefs, script scene plans, visual prompts, and performs vision-based QC evaluations. | Receives verified, contained image paths and grounded evidence text. |
| **Vertex Veo** | Generates raw video scene clips from keyframes and motion prompts via `predictLongRunning`. | Unchanged. Operation IDs checkpointed before polling. |
| **Product Video QC** | Enforces Image QC, Keyframe QC, and Video QC against rubrics and reference digests. | Fail-closed; verifies byte hashes on disk. |
| **HITL Approvals** | Enforces 5 human gates: Product Lock, Brief, Scene Plan, Storyboard, Final Video + Login/MFA intervention. | Operator must approve before proceeding. |
| **Export Packaging** | Assembles final MP4 composite with verified metadata, thumbnail, and exact lineage. | Strictly requires verified PASS QC report matching 6-tuple lineage. |

---

## 5. Domain Data Contracts

### 5.1 BrowserCaptureRequest

```python
@dataclass(frozen=True)
class BrowserCaptureRequest:
    workflow_id: str
    capture_id: str
    target_url: str
    owner_user_id: str
    project_id: str
    wait_selector: str | None = None
    capture_media: bool = True
    max_media_count: int = 12
    timeout_seconds: float = 30.0
    idempotency_key: str = ""
    viewport_width: int = 1280
    viewport_height: int = 720
```

### 5.2 BrowserEvidenceArtifact

```python
class EvidenceKind(str, Enum):
    SCREENSHOT = "screenshot"
    DOM_SNAPSHOT = "dom_snapshot"
    PRODUCT_IMAGE = "product_image"
    PRODUCT_VIDEO = "product_video"
    EXTRACTED_METADATA = "extracted_metadata"

@dataclass(frozen=True)
class BrowserEvidenceArtifact:
    artifact_id: str
    kind: EvidenceKind
    workspace_relative_path: str
    sha256: str
    source_url: str
    mime_type: str
    byte_size: int
    captured_at: str
    visual_description: str = ""
```

### 5.3 BrowserCaptureResult

```python
class BrowserCaptureStatus(str, Enum):
    COMPLETED = "completed"
    BLOCKED_FOR_LOGIN = "blocked_for_login"
    BLOCKED_CAPTCHA = "blocked_captcha"
    FAILED = "failed"

@dataclass(frozen=True)
class BrowserCaptureResult:
    workflow_id: str
    capture_id: str
    source_url: str
    canonical_url: str
    captured_at: str
    status: BrowserCaptureStatus
    page_title: str
    evidence_artifacts: tuple[BrowserEvidenceArtifact, ...]
    extracted_text_summary: str = ""
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

## 6. State Machine & Lifecycle Transitions

```
[PENDING]
   │
   ▼
[BROWSER_RUNNING]
   │
   ├───> [BROWSER_BLOCKED_FOR_LOGIN] ──(Operator logs in / solves CAPTCHA)──┐
   │                                                                        │
   ├───> [FAILED / QUARANTINED] (Non-retryable network / containment error) │
   │                                                                        │
   ▼                                                                        │
[CAPTURED] <────────────────────────────────────────────────────────────────┘
   │
   ▼
[INGESTED] (Artifacts hashed and written to workspace)
   │
   ▼
[PRODUCT_LOCK_PENDING] ──(Product Intelligence builds Resource Pack)
   │
   ▼
[LOCKED] ──(Gate 1: Operator Approves Product Lock)
   │
   ▼
[VERTEX_PROCESSING] ──(Gemini Brief -> Gemini Script -> Gemini Storyboard -> Veo Render)
   │
   ▼
[READY_FOR_NEXT_GATE] ──(Gates 2, 3, 4, 5 HITL verification)
```

---

## 7. Failure, Timeout, & Recovery Model

1. **Browser Crash / Subprocess OOM**: Playwright subprocess restart is managed per capture turn. If Chromium crashes, the adapter attempts 1 retry with clean temporary profile.
2. **Navigation Timeout**: Fixed 30s deadline per URL. On timeout, returns status `failed` with code `BROWSER_TIMEOUT`.
3. **Login / MFA / CAPTCHA Detection**: If selectors indicate login wall, Cloudflare turnstile, or captcha, immediately yields `status=BLOCKED_FOR_LOGIN` or `BLOCKED_CAPTCHA`. The workflow aggregate pauses in `WAITING_FOR_OPERATOR` state.
4. **Partial Downloads**: All media downloads are staged in `.tmp_downloads/` and moved atomically with SHA256 validation to `workspace/references/`. Incomplete files are cleaned up immediately.
5. **Replay & Restart Safety**: The outbox worker checks `browser_capture_records` in SQLite. If `capture_id` with matching request digest already exists in `completed` state, it returns existing record without re-opening the browser.
6. **Veo Re-submission Prevention**: Existing Veo operation checkpointing (`video_factory_scene_operation`) is preserved. Polling resumes using `provider_operation_id` without issuing new submit calls.

---

## 8. Security & Redaction Boundaries

1. **Credential Hygiene**: No cookies, session tokens, passwords, or `Authorization` headers are written to SQLite, logs, or model prompts.
2. **URL Sanitization**: Query parameters matching `token`, `auth`, `key`, `signature`, `session_id`, `api_key` are redacted in logs and aggregate records.
3. **Workspace Containment**: Ingested files are validated using `ProductVideoWorkspaceLayout.resolve_path()` to ensure they reside strictly within the project workspace directory. Absolute traversal (e.g. `../../etc/passwd`) is rejected immediately.
4. **Prompt Injection Defense**: Raw HTML/DOM text extracted from the browser is wrapped in structured JSON data objects (`untrusted_web_evidence`) and never interpolated into model system instruction blocks.

---

## 9. HITL (Human-in-the-Loop) Governance

Playwright automation is strictly confined to data gathering. It cannot:
- Bypass **Gate 1: Product Lock** (operator must verify grounded identity and claims).
- Bypass **Gate 2: Brief Approval** (operator approves creative angle).
- Bypass **Gate 3: Scene Plan Approval** (operator approves scene breakdown).
- Bypass **Gate 4: Storyboard Approval** (operator approves visual keyframes).
- Bypass **Gate 5: Final Video Approval** (operator approves composite MP4).
- Solve auth walls autonomously (triggers operator notification).

---

## 10. Migration & Feature Gating

1. **Configuration in `config.yaml`**:
   ```yaml
   product_video:
     browser_capture:
       enabled: true
       provider: "playwright" # "playwright" | "pi_mcp" | "mock"
       headless: true
       timeout_seconds: 30
   ```
2. **Zero `HERMES_*` Secret Envs**: Secret-free operational parameters live in `config.yaml`.
3. **Graceful Fallback**: If Playwright is not installed (`playwright not found`), falls back to static PDP URL fetching or explicit operator manual reference upload with clear diagnostic messaging.
4. **Zero Vertex Breaking Changes**: Vertex API schemas, endpoints, and credentials remain 100% intact.
