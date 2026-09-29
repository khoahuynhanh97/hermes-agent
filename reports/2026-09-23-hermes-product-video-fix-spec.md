# Hermes Product Video — Technical Fix Specification

- **Date:** 2026-09-23
- **Authority:** [Verified Fix Backlog](2026-09-23-hermes-product-video-verified-fix-backlog.md), supported by the [post-refactor verification](2026-09-23-hermes-product-video-post-refactor-verification.md) and the [Product Video master spec](../docs/superpowers/specs/product-video-master-spec.md).
- **Status:** Specification only. No production code or tests were modified in this pass.

## 1. Purpose

Define the observable contracts for the verified fixes so an implementation plan can be written without another architecture review. **MUST** and **MUST NOT** are binding requirements; **SHOULD** denotes a preferred behavior that needs an explicit exception if omitted. This document distinguishes provider-substituted offline evidence from a live configured run.

The target is one controlled, operator-reviewed real Product Video first, followed by safe concurrent paid operation. It does not authorize a deployment, provider charge, gate bypass, or redesign.

## 2. Scope

### Fix Scope

| Backlog issue | Disposition | Reason and boundary |
| --- | --- | --- |
| **FIX-001** Provider readiness / Flow | **IN CURRENT FIX SPEC** for truthful selection/readiness; full Flow operation **OPTIONAL / PRODUCT DECISION** | A real run requires a selected working provider. Vertex-only acceptance may leave Flow unavailable. The missing provider selection on this review host is **CONFIGURATION ONLY**, not a separate code defect. |
| **FIX-002** VF storyboard write | **IN CURRENT FIX SPEC** | A failed canonical write currently permits downstream paid work. Required for Milestone A. |
| **FIX-003** PI grounding | **IN CURRENT FIX SPEC** | Current dossier transformation can misstate support and source identity. Required for meaningful real content acceptance. |
| **FIX-004** End keyframe | **IN CURRENT FIX SPEC** | Current scene/frame mapping is wrong. Milestone A may support an explicit omission policy, but must reject unsupported generated/required end frames before paid work. |
| **FIX-005** Keyframe first submit | **IN CURRENT FIX SPEC** | Required for Milestone B, not an isolated single-worker happy run. |
| **FIX-006** VF project write conflict | **IN CURRENT FIX SPEC** | Required for Milestone B same-project parallel writers. |
| **FIX-007** Video QC scene regeneration | **OPTIONAL / PRODUCT DECISION**; default **DEFERRED UNTIL AFTER INITIAL REAL E2E** | Current non-PASS QC safely blocks progression. The master spec does not require automatic scene regeneration for the first happy run. |
| **FIX-008** MCP contract tests | **IN CURRENT FIX SPEC** | Five stale fixture/assertion failures keep formal regression signoff red; direct-caller compatibility still needs audit. |
| **FIX-009** Export provenance | **DEFERRED UNTIL AFTER INITIAL REAL E2E** | Exact byte, approval and Video QC checks already work. Full metadata remains required before claiming complete master-spec §10.2 compliance; this deferral narrows only the initial diagnostic run, not that obligation. |
| **FIX-010** Image reacquisition | **OPTIONAL / PRODUCT DECISION** | A product with two eligible images can pass the current safe Image QC gate. Automatic acquisition is not a proven first-run requirement. |
| **FIX-011** Shared provider/profile capacity | **IN CURRENT FIX SPEC** for Milestone B | Batch size three and outbox leases do not establish cross-worker provider quota or Flow profile exclusivity. No observed collision is claimed. |

There is no standalone configuration-only fix ticket. The controlled-run configuration must name the selected provider and usable credentials/session; configuration on this review host was unset. Legacy forwarding shims, daily importer cleanup and wiring `ProductImageCleaner` merely because it exists are outside the fix scope.

### Scope corrections from source inspection

1. **FIX-007 is conditional recovery, not a current QC failure.** `handlers.py:2177-2189` blocks non-PASS results; the master spec §9.3 requires this fail-closed behavior, not automatic retry.
2. **FIX-008 is a contract reconciliation, not permission to relax production validation.** The five reproducible tests fail against required lineage/keyframe/QC checks. Each is classified in FIX-008; a configured direct-caller audit is still required before ruling out an external compatibility defect.
3. **FIX-011 capacity evidence is limited.** The current three-product offline batch passes. A ten-product exercise is a later stress test, not evidence of a present three-product collision or a reason to change the intake cap.

## 3. Current Verified Baseline

- The completed combined run `uv run pytest tests/hermes_personal tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py -q` produced **1,108 passed, 5 failed, 46 warnings** in 162.97 s. The focused offline production-style selection produced **51 passed**. Startup imports, CLI help and Ruff passed (verification report §15).
- For this specification, `uv run pytest tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py -q --tb=short` was rerun read-only: **34 passed, 5 failed** in 7.24 s. The five exact cases are listed in FIX-008. No other test was rerun for this document.
- Offline tests verify the five gates, atomic intake, persisted workflow/outbox, V2 creative contracts, image/keyframe/video QC controls, scene operations, composition and strict export. They substitute external providers. **No live PI, model, evaluator, keyframe, Vertex video or authenticated Flow acceptance was performed.**
- Read-only Flow exercise in the verification produced a synthetic `submitted` state with no real browser job; a fresh instance could not look up the request. On this host the selected `video_factory.render_provider` resolved to unset. These observations do not generalize to every deployment.

## 4. Target Milestones

### Milestone A — Controlled single-product real E2E readiness

Required: FIX-001 readiness/explicit selected provider, FIX-002, FIX-003, FIX-004 and FIX-008; one configured real provider path, all five operator approvals, authentic QC and an inspected immutable export. **Full Flow browser operation belongs here only if Flow is selected.** If Vertex alone is selected, Flow must be unavailable/unselectable and the live test must exercise Vertex. A scene asking for unsupported end-frame conditioning must be rejected before paid generation; a documented `omitted` policy can allow a start-only scene.

Passing Milestone A requires both a green offline combined gate and the separate live evidence defined in §9. FIX-005/006/011 are not prerequisites for an explicitly isolated one-worker run without parallel writers.

### Milestone B — Concurrent / automated production readiness

Required: FIX-005, FIX-006 and FIX-011, with Milestone A behavior preserved. The workload may use multiple workers/products and paid provider calls only after duplicate-first-submit, lost-update, provider-capacity and, if Flow is enabled, browser-profile ownership are bounded and tested. This milestone does not automatically raise the current daily intake cap of three.

### Milestone C — Recovery, lineage and optional hardening

FIX-009 completes master-spec export provenance before full metadata signoff. FIX-007 and FIX-010 are implemented only if the product decisions in §11 require automatic recovery; otherwise their safe blocked/manual paths remain the contract. None is silently promoted into Milestone A. A decision to require full §10.2 metadata at first-run signoff moves FIX-009 to A.

## 5. System Invariants

### Workflow and approvals

1. A stage advances only after every canonical write required by that stage has succeeded and is bound to the current workflow, project, artifact/version and owner.
2. Product Lock, Creative Brief, Scene Plan, Storyboard and Final approvals remain authoritative. A retry or replay cannot synthesize, reuse for changed bytes, or bypass an approval.
3. Image, Keyframe or Video QC other than authentic current **PASS** blocks downstream eligibility. `UNKNOWN`, missing and stale reports are non-PASS.

### Product Intelligence and creative grounding

4. Persisted PI snapshot/pack records, tied to the locked product and variant, are the source for creative claims. A transformation preserves claim ID/text, support semantics, evidence IDs and source identity; an unsupported or untraceable claim never becomes verified.
5. Official-source selection is based on actual PI/source metadata and product identity. A vendor host suffix is not generic product logic.

### Video Factory and paid work

6. WF references to a storyboard/media version point to canonical VF state that exists. Paid keyframe generation cannot start until the matching VF storyboard is present.
7. Distinct valid VF writes cannot silently erase one another. A stale update is detected or safely merged without weakening owner isolation.
8. An enabled provider is ready only when it can actually perform its selected operation. The provider choice is explicit, and the durable pin never changes after the first submission claim. No synthetic slideshow fallback is introduced.
9. One logical paid operation/attempt has at most one first submission, even when two workers receive the same work. Unknown paid outcomes are reconciled or held for operator action rather than blindly resubmitted.

### Scene/keyframe identity and QC recovery

10. `scene_id` identifies one approved scene. `frame_id` and `frame_role` distinguish its START and optional END keyframes; frame count does not alter scene count or order.
11. Every required frame is checked against its exact bytes, digest, QC receipt and package version. A changed frame or prompt invalidates dependent clip, composite, QC and Final approval.
12. Recovery retains failed artifacts/attempt IDs for audit. A new paid correction has a distinct authorized attempt, bounded retry policy and fresh dependent QC.

### Final export

13. Export consumes only the approved canonical composite whose full decode, technical probe, SHA-256 and authentic SQLite PASS Video QC match the exact bytes and Final approval. Packages remain immutable and versioned.
14. The current strict lineage, identity, owner and admission checks are not weakened to make obsolete tests pass. Offline substitution is never labeled live verified.

## 6. Fix Specifications

### FIX-001 — Truthful render-provider readiness and Google Flow operation

#### Problem

The configured Flow adapter can report availability based on Playwright importability and return a synthetic submitted operation without a usable authenticated browser or recoverable external job.

#### Current Behavior

`integrations/video_factory/server.py::_video_provider` reads `video_factory.render_provider` and constructs `GoogleFlowPlaywrightProvider.from_config()` without a page/session (`server.py:1705-1758`). `google_flow_provider.py:56-173` treats an installed dependency as readiness, stores generated `gflow_op_*` IDs in process memory and returns `running` for an unknown ID. `SceneRenderRuntime` already persists provider pins and scene operation state (`scene_renderer.py:432-603,850-1100`). The offline restart probe found no Flow request after a new instance; no authenticated browser was exercised.

#### Required Behavior

**A — selection/readiness, unconditional:** A controlled run MUST name one selected official provider in resolved configuration. Missing or unsupported selection MUST return a clear configuration/unavailable result before paid scene submission. Flow MUST advertise unavailable unless the actual browser context, authenticated session, ownership and job/reconciliation capabilities required for that operation are usable. Vertex-only selection MUST NOT silently select or fall back to Flow; pre-submit fallback, if ever configured, MUST be explicit and observable. An already pinned operation MUST resume only with its pinned provider.

**B — full Flow, conditional on selection:** If Flow is selected for acceptance, its adapter MUST use an authenticated owned browser session to submit a real job; bind a real, externally verifiable operation identity to the durable scene operation; poll it to a validated clip or terminal failure; and reconcile the same request after process restart. Unknown IDs MUST NOT be represented as indefinitely running. A browser profile MUST have exclusive active ownership (also FIX-011). If Vertex-only acceptance is chosen, full Flow operation is deferred and Flow remains unavailable.

#### Invariants

- `provider_kind` stored with a scene operation is immutable after the submission claim.
- A `submitted` result represents externally accepted work, never a fabricated local token.
- Losing a browser session after submission does not cause a new provider charge or a provider switch.

#### Affected Components

- **MODIFY:** `integrations/video_factory/google_flow_provider.py` for readiness and, conditionally, full Flow; `integrations/video_factory/server.py::_video_provider` or its immediate readiness boundary for truthful selected-provider handling; configured provider guidance if its Flow example remains misleading.
- **VERIFY ONLY:** `integrations/video_factory/scene_renderer.py` selection/pinning/reconciliation; `integrations/video_factory/vertex_provider.py` selected Vertex path; `product_video/cli.py` doctor/preflight.
- **UNCHANGED:** the provider-neutral operation store, admission/approval gate, and video QC/export checks unless a concrete contract mismatch is found.

#### Data / Contract Changes

The existing `video_factory.render_provider` setting and `VideoGenerationRequest/Result` plus durable `provider_kind/provider_operation_id` remain the contract. **No domain or workflow schema change is required for truthful unavailability.** Full Flow may need durable session/profile ownership metadata; the implementation plan must use the existing scene-operation identity and may add only data necessary to reconcile real Flow jobs. A locally fabricated historical `gflow_op_*` value is not evidence of external work and must be marked ambiguous/unrecoverable, not silently adopted.

#### State / Transition Changes

`unconfigured/unavailable → PROVIDER_UNAVAILABLE` with no paid call; `ready + planned → provider pinned/submitting → real submitted external ID → running/completed or terminal failed`. A lost selected provider after submission enters `RECONCILIATION_REQUIRED` or operator-blocked state, never a fallback provider. A previously synthetic Flow ID requires explicit reconciliation before any new attempt.

#### Failure Behavior

Missing selection/session/auth/profile lock: **PROVIDER_UNAVAILABLE/BLOCKED** before submission. Transient polling failure with known real ID: **RETRYABLE** on the same pinned operation. Unknown or ambiguous result: **OPERATOR_REQUIRED/RECONCILIATION_REQUIRED**, with no guessed completion. Definitive provider rejection: **PERMANENT** for that attempt, allowing only an authorized new attempt if product policy permits.

#### Retry / Idempotency Behavior

Normal poll and process restart reuse the real provider ID. Duplicate worker delivery observes the same durable pin/operation; it cannot create a second first submit. A changed request digest conflicts. Vertex-only replay never probes Flow.

#### Backward Compatibility

Existing Vertex scene-operation rows and current CLI/API request shapes remain valid. Existing Flow rows containing only synthetic IDs are not treated as completed or safely resubmittable; they require operator reconciliation. No bulk migration of VF projects is justified.

#### Acceptance Criteria

- **HFX-AT-001:** With Playwright installed but no usable authenticated browser/session, Flow readiness is false and no provider submit or durable external ID is recorded.
- **HFX-AT-002:** A Vertex-only configured run selects Vertex, refuses silent Flow fallback, and resumes a submitted Vertex operation with the same pin.
- **HFX-AT-003 (conditional):** If Flow is enabled, submit yields a real verifiable operation; a fresh process reconciles and polls it to a decodable clip or terminal failure under exclusive profile ownership.
- **HFX-AT-004:** Missing selection reports a setup error before paid work; the review-host unset configuration is not mislabeled a source defect.

#### Required Tests

- **UNIT:** Readiness predicate with dependency present but session absent; unknown-operation result.
- **INTEGRATION:** Selected-provider mapping and durable pin; existing operation resumed with a different configured default.
- **RESTART / RECOVERY:** Same request and real operation ID after a new provider instance; ambiguous synthetic ID remains blocked.
- **PROVIDER CONTRACT:** Vertex selection/no silent fallback; Flow adapter contract if enabled.
- **LIVE ACCEPTANCE:** One real Vertex clip for Vertex-only scope, or one real Flow clip plus restart reconciliation for Flow scope. Offline adapter tests cannot satisfy this level.

#### Explicit Non-goals

No new provider family, slideshow fallback, broad provider abstraction redesign, or mandatory Flow browser implementation in a Vertex-only first acceptance.

### FIX-002 — Fail closed on Video Factory storyboard persistence

#### Problem

The workflow can continue into paid keyframe work after its canonical VF storyboard write throws or returns an unsuccessful result.

#### Current Behavior

After an approved Scene Plan, `product_video/handlers.py:1283-1315` calls `video_client.create_storyboard()` inside `except Exception: pass` and then compiles/submits keyframes. The handler also does not establish success from the returned value. `integrations/video_factory/server.py:1917-1931` requires the canonical VF storyboard at render. Existing offline happy-path tests do not inject a VF write failure (verification §6/§16).

#### Required Behavior

After the approved Scene Plan, the workflow MUST verify a successful VF storyboard persistence result for the same owner, workflow, project, approved plan identity/version and intended scene IDs **before** keyframe preparation or provider submission. An exception, explicit `ok=false`, missing project, mismatched persisted storyboard or ambiguous write outcome MUST stop the stage and surface a retryable or operator-visible failure. The Storyboard approval candidate MUST NOT appear until this boundary succeeds.

#### Invariants

- One approved plan maps to one canonical VF storyboard version at this handoff.
- No paid keyframe call is made while that required VF state is missing or unconfirmed.
- A successful retry does not create a second inconsistent storyboard or bypass Scene Plan approval.

#### Affected Components

- **MODIFY:** `product_video/handlers.py` handoff and result validation; immediate `VideoFactoryMCPClient.create_storyboard` response handling only if needed to expose canonical success.
- **VERIFY ONLY:** `integrations/video_factory/server.py::create_storyboard/render`, workflow outbox retry semantics, approval binding and the existing storyboard version contract.
- **UNCHANGED:** keyframe provider/QC rules, five approval gates, VF repository ownership checks.

#### Data / Contract Changes

**NO DATA CONTRACT CHANGE** is required if the client already returns enough identity/version to confirm the write. If it does not, the response contract must expose the persisted storyboard/project/scene-plan binding; no new workflow event or separate database is presumed. Existing stored VF storyboard rows remain valid.

#### State / Transition Changes

`ScenePlan APPROVED → VF storyboard write → verified persisted VF storyboard → keyframe preparation/submission → Storyboard candidate`. On failed/ambiguous write: `ScenePlan APPROVED → RETRYABLE or OPERATOR_REQUIRED`, with no downstream transition. If a write succeeded but acknowledgement was lost, retry first verifies the canonical persisted value and converges on it.

#### Failure Behavior

Transient VF storage/transport failure is **RETRYABLE** through the existing job/outbox. Identity/version mismatch or conflicting storyboard is **CONFLICT/OPERATOR_REQUIRED**. Invalid approval remains **BLOCKED**. Exceptions and unsuccessful return values are never swallowed.

#### Retry / Idempotency Behavior

Normal retry and restart use the same intended storyboard identity/idempotency key. Duplicate delivery may observe an already matching canonical storyboard and continue once; a divergent one conflicts. Concurrent duplicate handlers may not launch keyframes until each sees the same confirmed canonical write.

#### Backward Compatibility

Existing approved plans and VF storyboard rows remain readable; no historical migration is required. Existing CLI/API calls retain their inputs. An already advanced workflow lacking a VF storyboard is not falsely treated as valid; it must be reconciled before render or approval.

#### Acceptance Criteria

- **HFX-AT-005:** Injected VF exception and `ok=false` return each leave the stage before keyframe submission and before a Storyboard gate candidate; the failure identifies the project/operation.
- **HFX-AT-006:** Failed-then-successful retry yields one matching VF storyboard with the approved scene IDs, and downstream paid submission occurs only after confirmation.
- **HFX-AT-007:** A persisted storyboard for another owner/project or incompatible plan version conflicts rather than authorizing work.

#### Required Tests

- **UNIT:** Handler exception, unsuccessful response and mismatched success payload.
- **INTEGRATION:** Real VF repository/client write then read-back binding, including lost acknowledgement.
- **WORKFLOW:** Failed write → no keyframe call/gate → retry → one canonical storyboard and normal gate.
- **RESTART / RECOVERY:** Outbox replay converges on an existing matching write.

#### Explicit Non-goals

No handler/module move, new distributed transaction framework, relaxation of approvals, or unrelated storyboard redesign.

### FIX-003 — Preserve PI claim-specific evidence and source identity

#### Problem

The current PI-to-creative transformation uses one pack-wide evidence list for every claim, labels every carried claim supported, and recognizes official sources through a Xiaomi-specific host suffix.

#### Current Behavior

`product_video/handlers.py::_locked_research_dossier` merges locked pack data but builds `claims` from `resource_pack.claims` with generated IDs, `status="supported"` and the same `provenance.supporting_evidence_ids` for each; its `official_sources` filter is `host.endswith("mi.com")` (`handlers.py:231-359`). `product_video/mcp_adapters.py:264-403` requires persisted snapshot and pack IDs and passes their raw results. `creative/dossier.py:82-111` accepts only supported/verified/confirmed claims with evidence, and `creative/contracts.py:135-145` currently represents verified claims as ID/text/evidence refs. The adapter's persistence prerequisite is sound; the transformation is not.

#### Required Behavior

The locked PI snapshot/pack for one canonical product and variant MUST determine claim identity, exact text, support status, specific evidence references and source identity. Only claims already supported by verifiable claim-specific evidence enter `ResearchDossier.verified_claims`; unsupported, restricted, unknown and cross-product claims remain excluded or restricted, never promoted by a pack-wide evidence list. Each referenced evidence/source ID MUST resolve to the same locked product/snapshot/variant where that relationship is available. Official sources MUST follow source provenance/classification from PI or a vendor-neutral validated source rule; they MUST NOT require a particular vendor domain. Missing PI claim relationships fail closed for the affected claim rather than fabricating support. Creative generation consumes the corrected dossier and the existing Image QC PASS prerequisite.

#### Invariants

- Dossier claim ID/text and each evidence reference trace to a persisted PI record; no claim borrows another claim's evidence.
- Inclusion in `verified_claims` represents PI-supported status, not a transformation default.
- A source URL is not made official merely because its host resembles the product brand, and a valid non-Xiaomi official source is not discarded by generic logic.

#### Affected Components

- **MODIFY:** `product_video/handlers.py::_locked_research_dossier` and its PI mapping tests; a narrow PI adapter response validation only if a required existing field is being discarded.
- **VERIFY ONLY:** `product_video/mcp_adapters.py` persisted snapshot/pack IDs; `product_video/creative/dossier.py` and `creative/contracts.py` support filtering; brief/script claim-reference validators; PI source metadata actually returned by the configured service.
- **UNCHANGED:** PI persistence store, Product Lock, Image QC eligible-asset checks, V2 creative generation/repair policy.

#### Data / Contract Changes

The intended logical contract is `{claim_id, text, support_status, evidence_refs[], source_refs[]}` tied to `snapshot_id/resource_pack_id/product_id/variant_id`. The current `ResearchDossier.verified_claims` can remain the supported subset `{claim_id,text,evidence_refs}`; excluded status is retained in canonical PI records or the existing restricted-claim view. **No new generic evidence store or DB migration is specified.** If the configured PI payload lacks claim-specific IDs/status/refs, the first implementation step is a narrow PI wire-contract correction or explicit unsupported-claim exclusion; it must not synthesize evidence from pack-level provenance.

#### State / Transition Changes

`persisted PI snapshot + matching pack + Image QC PASS → validated claim/source mapping → locked dossier → creative generation`. Missing/mismatched claim evidence yields claim exclusion or `GROUNDING_REQUIRED/OPERATOR_REQUIRED` when no usable grounded dossier can be formed; it cannot advance as a supported claim.

#### Failure Behavior

Unresolvable evidence or source relationship is **BLOCKED** for that claim. Missing canonical PI snapshot/pack remains **PERMANENT** for this attempt until correct data is supplied. A transient PI read is **RETRYABLE** without changing claim status. A dossier with no permissible factual claims may use observed visual descriptions only where the existing creative contract allows; it cannot invent specifications.

#### Retry / Idempotency Behavior

Rebuilding from the same locked PI/QC inputs produces the same normalized claim IDs, refs and dossier digest. A changed snapshot/pack/evidence relationship requires a new locked version and downstream approval/invalidation under existing rules. Duplicate workers do not create alternate synthetic IDs.

#### Backward Compatibility

Existing stored PI snapshot/pack records are read as-is. Existing dossiers with synthetic support are not silently grandfathered for new creative acceptance; they need revalidation against canonical PI evidence before use. No wholesale PI database migration is authorized. Current V2 brief/script API shapes remain valid for truly supported claims.

#### Acceptance Criteria

- **HFX-AT-008:** Two supported claims with distinct evidence remain distinct; neither gains the other's evidence, and an unsupported third claim is absent from `verified_claims`.
- **HFX-AT-009:** A non-Xiaomi product retains its validated official source; a cross-product or unknown evidence ID cannot mark a claim supported.
- **HFX-AT-010:** Persisted snapshot/pack plus Image QC PASS yields a stable dossier digest and valid brief/script claim references; invalid PI relationships produce a visible grounding failure or excluded claim.

#### Required Tests

- **UNIT:** Multiple claims/statuses, multiple vendors, absent/unknown/cross-product evidence and deterministic ID/digest mapping.
- **INTEGRATION:** PI adapter persisted snapshot/pack fixture → dossier builder with source/variant verification.
- **WORKFLOW:** Product Lock/Image QC PASS → grounded dossier → V2 brief/script; failed grounding blocks creative paid work.
- **LIVE ACCEPTANCE:** Inspect PI evidence and creative claims for the selected real product; offline mapping tests alone do not verify the live PI service.

#### Explicit Non-goals

No Product Intelligence rewrite, extra generic evidence database, blanket prompt rewrite, or permission to infer claim support from a pack-wide list.

### FIX-004 — Preserve scene identity and optional end-frame semantics

#### Problem

A generated END keyframe is assigned a different `scene_id`, causing the render package to count it as another scene; the normalized video request consumes only the START frame.

#### Current Behavior

`creative/storyboard.py:100-305` creates `<scene>-start` and conditionally `<scene>-end` requests with distinct `frame_role`. `product_video/handlers.py:1315-1324` derives scene ID by stripping only `-start`. `integrations/video_factory/server.py:2104-2149` builds a `scene_id → keyframe` map and compares its size to scene count. `scene_renderer.py:170-250` prepares start-only `reference_image_paths`. `VideoGenerationRequest` has no named end-frame input (`ports.py:65-78`). The existing adversarial test checks request creation, not a two-frame render handoff.

#### Required Behavior

Every generated keyframe MUST carry the approved `scene_id` independent of `frame_id`, plus a role `START` or `END`. One approved scene produces one render-scene entry and exactly one required START frame; an END frame is optional according to the V2 `end_keyframe_policy`. The package must validate both frame hashes and QC bindings without increasing scene count. The provider-neutral scene request must represent the optional END separately from the START, with its `frame_id`, path, SHA-256, package digest and QC receipt; the START remains the primary conditioning image for backward-compatible start-only requests. A provider that supports first/last-frame conditioning must consume the approved END. A provider that cannot consume it MUST reject `generated/required` before paid keyframe/video work, unless an explicit product-approved omission policy for that scene permits a START-only request. An `omitted` policy retains its reason. No END is silently discarded.

#### Invariants

- Scene count and render order derive only from approved scene IDs, not number of frames.
- A scene has at most one approved frame per role for the same package version.
- A changed END frame or QC receipt changes the request identity/digest and invalidates dependent media/approval just like a changed START.

#### Affected Components

- **MODIFY:** `product_video/handlers.py` frame/scene packaging; `integrations/video_factory/server.py` package validation and scene mapping; `integrations/video_factory/ports.py::VideoGenerationRequest` or equivalent provider-neutral normalized request; `integrations/video_factory/scene_renderer.py` request/digest construction; enabled provider adapter only if it claims END support.
- **VERIFY ONLY:** `creative/storyboard.py` request policy, keyframe QC receipt/package digest, storyboard frame count, provider capability declaration.
- **UNCHANGED:** required START-frame QC gate, approved scene order, Video QC and final export byte checks.

#### Data / Contract Changes

The storyboard package's generated-frame entries require stable `scene_id` and explicit `frame_role`, while existing `frame_id` values remain valid. Render mapping is logically keyed by `(scene_id, frame_role)`; scene count is keyed by `scene_id`. The normalized provider-neutral request gains an **optional role-tagged END input** with frame ID, path, digest and QC binding; its absence preserves start-only callers. The request digest and durable operation identity include the END binding or explicit omission policy, so changed END bytes cannot reuse an old clip. No new scene ID, DB project migration or mandatory END generation is required.

#### State / Transition Changes

`V2 scene policy → capability check → START [and permitted END] keyframe generation → both frames QC/package binding → one render request for scene`. Unsupported `required/generated` policy stops at capability check, before paid work. A changed END frame after approval returns to keyframe QC/Storyboard approval and invalidates clip/composite/Video QC/Final approval through existing invalidation rules.

#### Failure Behavior

Missing required END, duplicate role, wrong scene, missing/changed bytes or stale QC is **BLOCKED** before video submission. Unsupported provider capability is **PROVIDER_UNAVAILABLE/OPERATOR_REQUIRED** before paid generation, never a silent omission. A transient render failure remains **RETRYABLE** under the same scene request/operation rules.

#### Retry / Idempotency Behavior

Replay of identical START/END/policy sees the same scene operation and does not resubmit accepted work. Any changed role input or omission policy yields a different request digest/version; an old provider operation cannot satisfy it. Duplicate worker delivery retains one scene count and one pinned video provider.

#### Backward Compatibility

Existing start-only packages/requests remain valid with END absent. Already saved `-end` frame IDs are not reinterpreted as scene IDs; affected packages must be revalidated or safely reassembled before new render. Current CLI/API start-only calls remain valid; no bulk VF project rewrite is presumed.

#### Acceptance Criteria

- **HFX-AT-011:** One scene with approved START+END keyframes remains one render scene; both frames pass identity, hash and QC/package validation and reach one provider-neutral render request.
- **HFX-AT-012:** A provider without END conditioning rejects `generated/required` before any paid keyframe/video submission, or accepts an explicitly approved omission policy with reason; it never silently drops END.
- **HFX-AT-013:** Changing END bytes/QC/role changes the request digest and invalidates prior clip, composite, Video QC and Final approval.

#### Required Tests

- **UNIT:** Scene/frame role mapping, duplicate-role/mismatch rejection and digest sensitivity to END.
- **INTEGRATION:** V2 scene → two generated frames/QC → VF storyboard package → one render request.
- **WORKFLOW:** Unsupported capability blocks before paid generation; explicit omitted policy follows start-only path.
- **PROVIDER CONTRACT:** Supported END reaches the adapter as a distinct binding; unsupported adapter fails before submit.
- **LIVE ACCEPTANCE:** Only if the chosen live provider claims END conditioning, inspect a real start/end-conditioned scene. A start-only first run does not establish that capability.

#### Explicit Non-goals

No new scene per END, forced END generation for every scene, implicit provider-specific option that bypasses the normalized contract, or reduction of keyframe QC.

### FIX-005 — Atomic first paid keyframe submission

#### Problem

Two workers can both pass the current read/checkpoint/submit sequence for one logical keyframe operation and invoke the paid provider twice.

#### Current Behavior

`integrations/video_factory/keyframe_provider.py:240-309` stores a row keyed by `operation_id` and checks a request digest, but `KeyframeRuntime.run` performs `get → save unknown → provider.submit → save result` without an atomic owner claim (`keyframe_provider.py:310-353`). A terminal `failed` row can also call `submit` again under the same operation ID. Sequential restart tests do not cover simultaneous first submissions. No duplicate live charge was observed; the race follows from source.

#### Required Behavior

Before any first paid submit, one worker MUST atomically claim ownership for a specific `operation_id + request_digest + attempt`. For two concurrent workers on the same logical attempt, **at most one** may call `provider.submit`; the other observes durable state, waits, or enters reconciliation. The claim and unknown-outcome checkpoint must survive process restart. A terminal failure may be retried only as a new explicit authorized attempt identity, or after proof that the prior attempt was never accepted/charged. Completed output reuse still requires exact SHA verification.

#### Invariants

- One operation ID cannot be reused with a different digest.
- At most one external first submit occurs per logical attempt, regardless of duplicate delivery.
- Ambiguous crash windows never trigger blind resubmission; paid work remains governed by budget authorization and keyframe QC.

#### Affected Components

- **MODIFY:** `integrations/video_factory/keyframe_provider.py::KeyframeOperationStore/KeyframeRuntime` claim and attempt handling; immediate operator-authorized retry caller if it currently reuses an attempt identity.
- **VERIFY ONLY:** workflow worker leases and budget admission; existing keyframe provider contract/reconciliation; operator keyframe regeneration path.
- **UNCHANGED:** scene-render operation claim/pin semantics, image hash checks and Keyframe QC gate.

#### Data / Contract Changes

The existing `video_factory_keyframe_operation` row and `operation_id/request_digest` are the durable identity. The storage contract must distinguish **unclaimed, claimed/submitting, externally identified, completed, terminal failed and ambiguous** outcomes for an attempt, with a single atomic winner. This may be represented using existing fields/conditional writes or the smallest additive claim/attempt metadata; the specification does not mandate a lock framework. Old rows without a proven external ID remain ambiguous rather than eligible for automatic resubmit.

#### State / Transition Changes

`absent/planned → atomic claim by one owner → submitting/unknown checkpoint → provider result ID → submitted/running/completed or failed`. Losing contenders observe the winner's row and never submit. A crash after claim but before durable provider ID yields `RECONCILIATION_REQUIRED`; a new authorized attempt is explicit, not an implicit loop from `failed`.

#### Failure Behavior

Digest mismatch is **CONFLICT/PERMANENT** for that operation. Contended claim is **RETRYABLE wait/observe**, not provider failure. Unknown provider outcome is **OPERATOR_REQUIRED/RECONCILIATION_REQUIRED**. Known terminal provider rejection is **PERMANENT** for its attempt; a separately authorized new attempt may follow. Missing/changed completed artifact remains **BLOCKED**.

#### Retry / Idempotency Behavior

Normal replay returns a SHA-verified completed output or polls the known provider ID. Restart with an ambiguous claim reconciles where the provider can prove request identity; otherwise it blocks. Duplicate worker delivery and simultaneous workers have the same at-most-once first-submit contract. A new attempt changes the durable logical identity and consumes only its own authorized budget.

#### Backward Compatibility

Existing completed rows remain readable and reusable after SHA validation. Existing `unknown` rows without a provider ID stay fail-closed. A small additive row migration is allowed only if necessary to express the atomic claim/attempt; existing CLI/API operation IDs are not silently rewritten.

#### Acceptance Criteria

- **HFX-AT-014:** Two workers with separate SQLite connections released on the same keyframe operation invoke the fake provider exactly once and converge on one durable operation identity.
- **HFX-AT-015:** Same operation ID with a different digest conflicts; crash between claim and result never causes automatic second submission.
- **HFX-AT-016:** A known completed result replays only if file SHA matches; terminal failure retry uses a distinct authorized attempt or verified safe reconciliation.

#### Required Tests

- **UNIT:** Digest conflict, completed-file mismatch and failure/attempt semantics.
- **INTEGRATION:** SQLite atomic claim with two connections and a counted fake provider.
- **CONCURRENCY:** Simultaneous first submit yields one call, including repeated delivery.
- **RESTART / RECOVERY:** Crash-window unknown result blocks or reconciles; known result is reused.
- **PROVIDER CONTRACT:** Existing keyframe provider result identity/poll behavior remains valid. No paid live test is required for the mutual-exclusion proof.

#### Explicit Non-goals

No new broker/distributed-lock service, no rewrite of workflow outbox, no bypass of operator authorization or keyframe QC.

### FIX-006 — Detect conflicting Video Factory project writes

#### Problem

Two writers that read one VF project can each save a whole-project snapshot, allowing the later write to erase fields committed by the first without detecting a conflict.

#### Current Behavior

`integrations/video_factory/repository.py:365-410::SQLiteVideoFactoryRepository.save` updates nearly every project column with `WHERE id=? AND owner_user_id=?` and does not compare an expected revision or changed field values. `integrations/video_factory/service.py` uses this repository for storyboard, generated scenes, timeline and final state. WF aggregate optimistic versioning protects a different row and does not prevent this VF lost update.

#### Required Behavior

A VF save based on an older project state MUST NOT silently overwrite a newer committed state. A conflicting save must return an explicit **CONFLICT** or perform a demonstrably safe merge of non-overlapping changes against the latest row. The caller may reread/reapply its intended update only while all owner, approval, version and media dependencies still hold. Sequential writes retain present behavior and owner isolation.

#### Invariants

- Every successful VF project write is based on the current durable state or a safe field-level equivalent.
- A conflict cannot erase previously committed storyboard, scene, timeline, approval or artifact fields.
- Owner identity and downstream approval invalidation remain authoritative.

#### Affected Components

- **MODIFY:** `integrations/video_factory/repository.py::save` and immediate `integrations/video_factory/service.py` save callers to propagate/retry conflicts safely.
- **VERIFY ONLY:** workflow aggregate versioning, render-batch/scene-operation tables, operator approval binding and final export.
- **UNCHANGED:** VF domain meanings, provider operations, source media layout, five gates.

#### Data / Contract Changes

The VF project-save contract must include a reliable expected-state predicate or equivalent targeted update that prevents stale whole-row overwrite. A monotonic row revision is one valid representation but is **not prescribed**; if chosen it is an additive DB field with default/backfill for historical rows. Existing semantic per-artifact version fields cannot be assumed to cover every whole-row mutation without proof. The repository port must expose conflict rather than returning success for zero/contended writes.

#### State / Transition Changes

`read revision R → compute intended update → save if still R → new durable state`; otherwise `CONFLICT → reread/revalidate → safe retry or operator block`. Two stale divergent saves cannot both report success while discarding either update. A same-project concurrent render/approval path follows this rule; different projects do not contend.

#### Failure Behavior

Stale state is **CONFLICT/RETRYABLE** only after revalidation; changed approval/artifact dependencies are **BLOCKED/OPERATOR_REQUIRED**. Missing or wrong-owner row is **PERMANENT** for that request. Storage errors remain visible and do not present a successful VF state.

#### Retry / Idempotency Behavior

An identical replay against already persisted intended state may succeed idempotently. A divergent stale replay conflicts. Concurrent workers may retry against current state, but cannot reuse a stale approval/QC binding. Process restart loads the durable latest state, not a cached project snapshot.

#### Backward Compatibility

Existing VF projects and CLI/API calls remain usable. If an additive revision is selected, historical rows receive a valid starting revision without rewriting project/media payloads. No migration of exported immutable packages is required.

#### Acceptance Criteria

- **HFX-AT-017:** Two stale readers of one project cannot both save divergent full-project snapshots successfully while losing one writer's state.
- **HFX-AT-018:** A resolved conflict retains both valid non-overlapping changes or reports an explicit unresolvable conflict; owner change is never accepted as a merge.
- **HFX-AT-019:** Sequential storyboard/render/composition/export and restart behavior remain green.

#### Required Tests

- **UNIT:** Repository conflict result and idempotent identical replay.
- **INTEGRATION:** Real SQLite stale-reader same-project writes; different-project isolation.
- **WORKFLOW:** Same-project scene/approval save conflict cannot lose an approved artifact.
- **CONCURRENCY:** Two connection/worker writers with an enforced interleaving.
- **RESTART / RECOVERY:** Reread current revision and safe retry; existing historical row loads.

#### Explicit Non-goals

No new database layer, wholesale VF data model redesign, broad migration, or forced whole-project CAS if a smaller equally safe conditional update proves the invariant.

### FIX-008 — Reconcile the five MCP tests with the strict contract

#### Problem

Five direct MCP tests assert older render/export contracts or error ordering and keep the combined validation gate red. The current strict lineage, keyframe/QC and final integrity checks are supported by newer tests.

#### Current Behavior

The read-only rerun of `tests/mcp_servers/test_video_factory_server.py` plus `test_video_factory_paid_contract.py` produced **34 passed, 5 failed**. The production entry points are `integrations/video_factory/server.py::render/export`; export checks required canonical `owner_user_id, project_id, workflow_id, artifact_id, artifact_version, sha256` before later checks (`server.py:3421-3443`), and V2 render requires approved generated keyframes and a keyframe QC receipt (`server.py:2104-2149`). Case-by-case classification:

| Failing test | Observed assertion | Classification and contract evidence |
| --- | --- | --- |
| `test_render_and_export_fail_closed_truthfully` | Expected `MISSING_RENDER_OUTPUT`; got `RENDER_LINEAGE_REQUIRED` | **STALE TEST** error-order assertion: `export({})` has no canonical lineage. |
| `test_render_submits_approved_storyboard_to_provider` | Expected `ok=True`; got `ok=False` | **STALE TEST** positive fixture: symbolic `asset://` storyboard lacks the generated V2 keyframe and QC package now required before paid render. |
| `test_deterministic_export_promotes_mp4_without_provider_call` | Expected `ok=True`; got `ok=False` | **STALE TEST** positive fixture: render result omits required `sha256` and does not establish all current canonical artifact/approval bindings. |
| `test_export_fails_when_caption_identity_is_pack_id_or_generic` | Expected `PRODUCT_IDENTITY_REQUIRED`; got `RENDER_LINEAGE_REQUIRED` | **STALE TEST** error-order assertion: its render result lacks workflow/artifact/version/SHA; its sample bytes are also not a valid decodable MP4. |
| `test_export_fails_without_valid_project_and_final_approval` | Expected project/final-approval codes; got `RENDER_LINEAGE_REQUIRED` | **STALE TEST** error-order assertion: all four subcases supply only `video_url`; canonical lineage validation runs first. |

These are source-supported classifications of **the test fixtures/assertions**, not a completed audit of any external direct MCP caller. A real compatibility regression must be recorded separately if that audit finds one.

#### Required Behavior

Positive direct-MCP tests MUST supply the current canonical render lineage, approved project/storyboard, generated keyframe/QC evidence, authentic final approval and exact PASS Video QC required by the behavior being tested. Negative tests MUST isolate their target guard by satisfying earlier prerequisites or explicitly assert the first current fail-closed error. The configured direct MCP callers MUST be inventoried and checked against the current contract; any valid caller broken by the changed contract needs a narrow compatibility/migration decision. Production checks MUST NOT be weakened solely to restore old tests.

#### Invariants

- Missing canonical lineage, stale/missing QC, invalid bytes, unapproved storyboard and wrong owner/project continue to fail closed.
- A green gate tests the current public contract, not just mocked successful return values.
- A direct caller finding is reported as a separate evidenced defect rather than silently folded into fixture updates.

#### Affected Components

- **MODIFY:** The five cases in `tests/mcp_servers/test_video_factory_server.py` and `tests/mcp_servers/test_video_factory_paid_contract.py`; direct-caller documentation/fixtures only if the audit shows they are stale.
- **VERIFY ONLY:** `integrations/video_factory/server.py::render/export`, current `tests/hermes_personal/product_video/test_export_integrity.py`, scene-render and production-integrity tests; configured direct MCP clients.
- **UNCHANGED:** canonical lineage/QC/approval/decode/SHA production guards absent a separately demonstrated defect.

#### Data / Contract Changes

**NO PRODUCTION DATA CONTRACT CHANGE** is required for the known five failures. Tests must use the existing render/export request/response contract and current validation order. A direct caller audit may reveal an external migration requirement; it does not pre-authorize a server schema change.

#### State / Transition Changes

No production state transition is changed. The test fixture moves from incomplete synthetic state to a valid approved/QC-bound state before asserting downstream behavior. Negative cases still observe the earliest failed precondition.

#### Failure Behavior

Missing lineage remains **BLOCKED** with `RENDER_LINEAGE_REQUIRED`; missing V2 keyframe/QC remains **BLOCKED** before paid render; invalid media and missing Final approval/QC remain **BLOCKED** at their respective guards. Test setup failure is not interpreted as a successful product path.

#### Retry / Idempotency Behavior

The deterministic export test must prove same-version same-bytes replay remains idempotent, and changed bytes/version are rejected or versioned under the existing contract. No provider call occurs during export. Test reruns have no production state migration.

#### Backward Compatibility

Current strict server behavior remains. Direct MCP callers using older permissive payloads are not presumed compatible; the audit determines whether they are obsolete fixtures, callers needing updated inputs, or a separately evidenced regression. Existing persisted canonical projects/artifacts are unchanged.

#### Acceptance Criteria

- **HFX-AT-020:** Each of the five named cases is reconciled to the current validation order/fixtures while retaining its original intended negative or positive assertion.
- **HFX-AT-021:** The exact combined `tests/hermes_personal` + two MCP-file command passes with zero failures, while lineage/QC/approval/invalid-byte/owner negative coverage remains.
- **HFX-AT-022:** Configured direct MCP callers are inventoried and exercised or contract-reviewed; any genuine caller break has an explicit defect/migration decision before formal acceptance.

#### Required Tests

- **UNIT:** The five named MCP cases with current fixtures/error precedence.
- **INTEGRATION:** Direct server render/export with real local VF/QC/approval records and decodable fixture media.
- **WORKFLOW:** Existing Product Video export-integrity and scene-render flows remain green.
- **RESTART / RECOVERY:** Existing deterministic export replay test stays idempotent.
- **PROVIDER CONTRACT:** Render test proves no provider submit when keyframe/QC prerequisites fail; valid provider fixture receives one approved request.
- **LIVE ACCEPTANCE:** Not required to fix stale tests; Milestone A separately requires a real selected-provider run.

#### Explicit Non-goals

No removal of render lineage, keyframe QC, final approval, exact Video QC or MP4 integrity checks to satisfy old expected codes.

### FIX-011 — Bound shared provider and Flow browser-profile capacity

#### Problem

Current batch and job leases bound coordinator/outbox work but do not establish a shared paid-provider in-flight limit or exclusive Flow browser-profile ownership across workers.

#### Current Behavior

`product_video/automation/coordinator.py:213-266` caps an intake batch at three; `workflows/worker.py:75-137` leases outbox jobs. `integrations/video_factory/google_flow_provider.py:47-53` has process-local operation maps. The scene and keyframe stores track operation identity but not a shared provider quota or browser-profile lease. Three-product offline tests pass; ten-product and live quota/profile contention were not tested. This is a production-capacity boundary, not an observed current collision.

#### Required Behavior

Before concurrent automated paid use, the runtime MUST bound each selected provider's in-flight paid work to an explicitly configured capacity shared across workers. Flow, if enabled, MUST grant at most one active owner of a given authenticated browser profile and release/recover ownership after worker death without allowing two simultaneous operators. Excess eligible work remains durably pending and resumes when capacity is available; timeout/rate limit cannot produce a second first submission for the same operation. Limits and profile identity are behavioral settings in `config.yaml`, not new user-facing non-secret environment variables.

#### Invariants

- Provider in-flight count never exceeds the configured cross-worker limit.
- One Flow profile has one active owner at a time; provider pin and operation identity remain stable while queued/retried.
- Capacity waiting does not consume a new approval or duplicate budget reservation/submission.

#### Affected Components

- **MODIFY:** Paid-call admission immediately around `integrations/video_factory/keyframe_provider.py::KeyframeRuntime.run` and `scene_renderer.py::SceneRenderRuntime.run` (or their existing shared caller), with durable capacity ownership; `google_flow_provider.py` profile ownership only if Flow is enabled; configuration schema/guidance for non-secret limits.
- **VERIFY ONLY:** `automation/coordinator.py` batch cap, `workflows/worker.py` leases, `workflows/budgets.py` paid authorization, keyframe first-submit FIX-005, VF conflict FIX-006 and scene-operation pin/reconciliation.
- **UNCHANGED:** intake cap of three, the five gates, provider-neutral scene request, and current no-broker architecture.

#### Data / Contract Changes

The capacity contract requires a configured provider limit and a recoverable shared ownership record for active slots/profile claims. The precise storage representation is not fixed; it must be durable and atomic across the SQLite-backed workers and keyed by provider plus profile where applicable. No new queue/broker is implied. Existing project/media/operation IDs remain valid.

#### State / Transition Changes

`eligible pending job → atomic capacity/profile claim → authorized provider operation → release on terminal result`. At limit: `pending/waiting` with no provider call. On worker death: lease expiry/reconciliation preserves the underlying operation pin and resolves capacity ownership before another worker proceeds.

#### Failure Behavior

No slot or busy profile is **RETRYABLE wait**. Invalid configuration is **PROVIDER_UNAVAILABLE/BLOCKED** before paid work. Rate limit or timeout is **RETRYABLE** only after reconciliation of the existing operation. Ambiguous paid outcome is **OPERATOR_REQUIRED**, never an automatic new submission. A profile ownership conflict is **CONFLICT**, not a second browser session.

#### Retry / Idempotency Behavior

Job replay reacquires capacity for the same durable operation and checks its provider state before any submit. Duplicate workers cannot hold the same profile or violate the capacity count. Restart reclaims expired ownership only after confirming no concurrent valid owner and reconciling any possibly accepted paid operation.

#### Backward Compatibility

Existing single-worker jobs and provider operation rows remain valid. A missing new limit uses a documented safe default or blocks multi-worker paid admission; it does not silently become unlimited. Flow-specific profile data is unnecessary for Vertex-only operation. No intake cap change or historical media migration is required.

#### Acceptance Criteria

- **HFX-AT-023:** Two workers cannot simultaneously own one Flow profile, when Flow is enabled; after owner death, queued work resumes without a duplicate paid scene operation.
- **HFX-AT-024:** Across separate workers, observed in-flight provider calls never exceed configured capacity and excess work remains durable.
- **HFX-AT-025:** Offline three-product smoke stays green; a staged ten-product fake-provider stress run shows isolated project/media paths and no duplicate paid-operation IDs without changing the current per-batch cap.

#### Required Tests

- **UNIT:** Capacity/profile configuration validation and waiting state.
- **INTEGRATION:** Shared SQLite ownership and terminal release across worker connections.
- **WORKFLOW:** Queued job survives contention and resumes through existing outbox.
- **CONCURRENCY:** Multi-worker capacity bound and exclusive Flow profile if enabled.
- **RESTART / RECOVERY:** Worker death, lease expiry and operation reconciliation before reclaim.
- **PROVIDER CONTRACT:** Rate-limit/timeout keeps one pinned operation and no duplicate first submit.
- **LIVE ACCEPTANCE:** One controlled capacity/quota exercise only when scaling paid production; fake-provider stress alone does not certify external quotas.

#### Explicit Non-goals

No new RabbitMQ/Kafka/Redis/DLQ, blanket increase of daily product cap, forced Flow profile machinery in a Vertex-only deployment, or claim that the current three-product offline test exposed a collision.

## 7. Cross-Fix Interactions

The matrix marks only a shared boundary or prerequisite. `S` = shared artifact/contract, `P` = prerequisite for the other fix's acceptance, `T` = test fixture/validation interaction, `—` = no direct dependency. It is symmetric except where the explanation gives direction.

| Fix | 001 Provider | 002 Storyboard | 003 Grounding | 004 End frame | 005 KF claim | 006 VF conflict | 008 MCP tests | 009 Lineage | 011 Capacity |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **001 Provider** | — | — | — | S | — | — | — | — | S |
| **002 Storyboard** | — | — | — | S | P | S | T | — | — |
| **003 Grounding** | — | — | — | — | — | — | — | P | — |
| **004 End frame** | S | S | — | — | S | S | T | S | — |
| **005 KF claim** | — | P | — | S | — | — | — | — | P |
| **006 VF conflict** | — | S | — | S | — | — | — | — | P |
| **008 MCP tests** | — | T | — | T | — | — | — | T | — |
| **009 Lineage** | — | — | P | S | — | — | T | — | — |
| **011 Capacity** | S | — | — | — | P | P | — | — | — |

- **001 ↔ 004:** END-frame capability must be checked against the *selected* provider before paid generation. Selecting Vertex versus Flow does not change scene identity.
- **001 ↔ 011:** Flow browser-profile ownership is conditional on enabling Flow; provider capacity is required for scaled Vertex work as well.
- **002 → 005 and 002 ↔ 004/006:** Canonical storyboard success precedes any keyframe claim. End-frame packaging shares the storyboard version; VF write protection must not overwrite that version.
- **003 → 009:** Export evidence lineage cannot be truthful while dossier claim support is synthetic. FIX-003 can pass independently of deferred export enrichment.
- **004 ↔ 005/006/009:** Frame-role and digest changes affect keyframe attempt identity, VF storyboard state and later keyframe provenance.
- **008 ↔ 002/004/009:** MCP positive render/export fixtures must use canonical storyboard/keyframe/QC and lineage contracts. Updating fixtures does not imply production changes to the other fixes.
- **005 + 006 → 011:** Capacity admission is insufficient if the same keyframe can submit twice or same-project VF writes can be lost. These are separate boundaries; neither FIX-005 nor FIX-006 depends on the other for its own proof.

FIX-007 and FIX-010 have no prerequisite for the initial happy path. If automatic Video QC recovery is later selected, it uses new attempt identities and safe VF updates from FIX-005/006 for concurrent paid use. If image reacquisition is later selected, new bytes must pass current Image QC; it does not depend on Flow or end-frame support.

## 8. Non-Regression Contract

The following verified behaviors remain binding unless an individual fix explicitly changes its immediate contract:

1. Five operator approval gates with exact owner/workflow/project/artifact/version binding, rejection and downstream invalidation.
2. Atomic product claim, workflow-created/ledger-marked crash recovery and the current three-product intake cap.
3. Workflow aggregate versioning, event/outbox transaction, worker leases, heartbeats, retries, quarantine and restart recovery.
4. Persisted PI snapshot/pack prerequisites and Product Lock requiring genuine Image QC PASS with at least two eligible sources.
5. Image decode, SHA, dedup, identity/risk/score checks; selected reference containment and SHA verification before keyframe generation.
6. V2 creative schema, evidence-bound claim references, validation and one bounded repair call.
7. Keyframe QC before Storyboard approval and existing operator-authorized keyframe regeneration.
8. Provider-neutral video scene request; durable scene operation ID, provider pin, no silent post-submit fallback and no still-image slideshow fallback.
9. Ordered clip validation, composition geometry/full decode and invalidation after changed media.
10. Exact Final approval and authentic SQLite PASS Video QC bound to the exported composite SHA; final decode, SHA and immutable/versioned export behavior.
11. Offline fake-provider coverage remains useful but cannot be presented as live acceptance. Existing compatibility shims and runbook entry points are not removed as part of these fixes.

Any regression test update under FIX-008 MUST continue to demonstrate the negative guards above. A new positive fixture may satisfy prerequisites; it cannot bypass them.

## 9. Acceptance Levels

| Level | Evidence required | What it does **not** establish |
| --- | --- | --- |
| **OFFLINE VERIFIED** | Current source imports; focused unit/integration/workflow, SQLite concurrency/restart and provider-contract tests pass with controlled substitutes; combined Product Video + MCP gate is green; exact failure-path assertions are observed. | External credentials, browser authentication, paid provider behavior, production quota or visual quality of a real product. |
| **LIVE PROVIDER VERIFIED** | For each *enabled* provider actually claimed ready, a configured authenticated request produces an externally verifiable operation ID, survives a new process where applicable, resolves to a real decodable artifact or terminal failure, and records provider/cost facts. For Flow, browser/profile ownership is also observed. | A complete Product Video through all five gates. A live Vertex result does not verify Flow. |
| **CONTROLLED SINGLE-PRODUCT E2E VERIFIED** | One real READY PI product and selected variant traverse persisted PI evidence, Image QC, V2 creative, real keyframe/QC, selected live video provider, all five inspected approvals, real Video QC and immutable export; an operator inspects frames across every scene, and independently confirms decode, SHA, lineage IDs and budget. Replay after worker restart does not resubmit accepted work. | Concurrent multi-worker safety or unselected provider support. |
| **CONCURRENT PRODUCTION VERIFIED** | Milestone A remains green; separate worker/SQLite connection tests prove one first keyframe submit, no VF lost update, bounded provider slots and (if enabled) exclusive Flow profile; a controlled live capacity/quota exercise confirms selected external provider behavior. Multiple products keep independent IDs, paths and spend. | Unlimited throughput or acceptance of a higher daily intake cap without a new decision. |

No level is promoted by naming a mock “live,” by seeded QC alone, or by an undecodeable or uninspected MP4. A release claim states the actual selected provider(s), data source and level achieved.

## 10. Traceability Matrix

The `HFX-AT-*` IDs refer to observable acceptance criteria in §6. “Proposed” means the test is required by this specification but not yet implemented; existing test names in §3 are baseline evidence only. Conditional rows are activated by the decisions in §11.

| Requirement ID | Backlog fix | Requirement | Acceptance test / evidence | Milestone |
| --- | --- | --- | --- | --- |
| **HFX-REQ-001** | FIX-001 | Flow unavailable without usable authenticated browser/session | HFX-AT-001; unit/provider contract | A |
| **HFX-REQ-002** | FIX-001 | Explicit Vertex selection, no silent Flow fallback, durable pin | HFX-AT-002; integration/restart | A |
| **HFX-REQ-003** | FIX-001 | Selected Flow produces real recoverable operation/clip | HFX-AT-003; provider contract + live Flow | A **if Flow selected** |
| **HFX-REQ-004** | FIX-001 | Missing selected provider stops before paid work | HFX-AT-004; config/preflight | A |
| **HFX-REQ-005** | FIX-002 | VF write failure prevents paid keyframes and gate | HFX-AT-005; handler fault + workflow | A |
| **HFX-REQ-006** | FIX-002 | Retry converges on matching canonical storyboard | HFX-AT-006/007; VF integration/restart | A |
| **HFX-REQ-007** | FIX-003 | Supported claims keep their own evidence/status | HFX-AT-008; mapping unit | A |
| **HFX-REQ-008** | FIX-003 | Vendor-neutral official-source and cross-product checks | HFX-AT-009; PI integration | A |
| **HFX-REQ-009** | FIX-003 | Locked PI/QC inputs give stable grounded dossier and creative refs | HFX-AT-010; workflow + live PI inspection | A |
| **HFX-REQ-010** | FIX-004 | One scene with START+END remains one render scene | HFX-AT-011; package→render integration | A |
| **HFX-REQ-011** | FIX-004 | Unsupported END policy rejected or explicitly omitted before paid work | HFX-AT-012; provider capability/workflow | A |
| **HFX-REQ-012** | FIX-004 | Changed END binding invalidates derived media/QC/approval | HFX-AT-013; digest/invalidation | A |
| **HFX-REQ-013** | FIX-005 | One atomic first paid keyframe submit per attempt | HFX-AT-014; two-worker SQLite | B |
| **HFX-REQ-014** | FIX-005 | Digest conflict/crash ambiguous outcome never resubmits blindly | HFX-AT-015/016; restart | B |
| **HFX-REQ-015** | FIX-006 | Stale VF project writer cannot erase committed state | HFX-AT-017; two-reader SQLite | B |
| **HFX-REQ-016** | FIX-006 | Conflict resolution preserves valid writes/owner isolation | HFX-AT-018/019; workflow/restart | B |
| **HFX-REQ-017** | FIX-008 | Each of five MCP cases uses current strict contract | HFX-AT-020; named MCP tests | A |
| **HFX-REQ-018** | FIX-008 | Combined gate green with negative guards intact | HFX-AT-021; exact combined pytest command | A |
| **HFX-REQ-019** | FIX-008 | Direct MCP callers audited for real compatibility | HFX-AT-022; caller inventory/review | A |
| **HFX-REQ-020** | FIX-011 | Enabled Flow profile has exclusive owner | HFX-AT-023; concurrency/restart | B **if Flow enabled** |
| **HFX-REQ-021** | FIX-011 | Shared in-flight paid provider limit holds | HFX-AT-024; multi-worker capacity | B |
| **HFX-REQ-022** | FIX-011 | Multi-product isolation survives staged stress | HFX-AT-025; three-/ten-product fake-provider smoke | B |
| **HFX-REQ-023** | FIX-009 | Export metadata resolves canonical research/media/attempt/QC chain | Deferred contract in §12; metadata integration + retained-store resolution | C; A if full §10.2 signoff required |
| **HFX-REQ-024** | FIX-007 | Non-PASS Video QC remains blocked; optional authorized scene retry invalidates/re-QCs | Deferred contract in §12; FAIL→authorized retry→new PASS workflow if selected | C **if selected** |
| **HFX-REQ-025** | FIX-010 | Replacement source bytes receive fresh eligibility/QC before Product Lock | Deferred contract in §12; replacement/stale-QC workflow if selected | C **if selected** |

## 11. Open Decisions

These choices change scope; none suspends independent FIX-002/003/005/006/008 work.

| Decision | Options | Scope effect |
| --- | --- | --- |
| **First real acceptance provider** | **Vertex only** / **Vertex + Google Flow** | Vertex-only requires truthful Flow unavailability and one live Vertex run. Including Flow activates full FIX-001 browser submission, durable reconciliation, exclusive profile ownership and a live Flow run in A. |
| **End-frame policy on a selected provider without END conditioning** | Reject `generated/required` before paid work / explicitly permit a documented `omitted` scene policy | Both require FIX-004 scene/role correction and honest package validation. END-conditioning live acceptance applies only if the selected provider claims it. Silent dropping is never an option. |
| **Initial Video QC recovery** | Safe operator-blocked/manual correction / automatic operator-authorized scene regeneration | First option defers FIX-007; second activates its bounded retry/invalidation/new-QC contract in A or C as the product decision states. Non-PASS always blocks. |
| **Insufficient image sources** | Manual replacement with fresh Image QC / automatic reacquisition now | First option leaves FIX-010 optional; second activates a governed acquisition/re-QC flow. Neither permits Product Lock with fewer than two eligible references. |
| **First-run metadata signoff** | Diagnostic acceptance with current truthful byte/QC metadata and retained stores / full master-spec §10.2 metadata at first signoff | First option defers FIX-009 to C before declaring full spec compliance; second moves its provenance acceptance to A. Export integrity checks remain mandatory in either case. |

The chosen provider and these policy decisions must be recorded before the corresponding live acceptance attempt. They do not imply an architecture or implementation choice.

## 12. Deferred Work

### FIX-007 — Optional governed Video QC scene recovery

**Current safe contract:** `qc/video_qc.py:355-436` may recommend `retry_scene_N`; `product_video/handlers.py:2177-2189` moves non-PASS to `WaitingForOperator`. No automatic scene-regeneration action consumes the recommendation. A failed scene cannot gain Final approval/export; the operator sees the failure. A documented manual route, if chosen, must lead to a new render/composite/QC without reusing stale approval.

**Conditional future contract:** A selected automatic action is tied to an explicit operator authorization, scene ID, attempt ID, maximum attempt count and budget. It retains old failed clip/QC, invalidates dependent composite/Video QC/Final approval, generates only the chosen scene as a new attempt, composes again and requires new PASS QC before approval. Duplicate delivery may not create two paid attempts. The test is FAIL → authorized bounded retry → new clip/composite → fresh QC/approval eligibility, with replay and stale-approval rejection. This is not Milestone A work unless the decision in §11 says otherwise.

### FIX-009 — Complete export provenance before full metadata compliance

**Current safe contract:** `integrations/video_factory/server.py:3421-3910` and `export_package.py` verify canonical render fields, final bytes, decode, exact Video QC and approval. The package provenance at `server.py:3824-3858` is partial; `product_video/mcp_adapters.py:609-620` may lose source URL during VF mirroring. These gaps do not authorize a bad MP4.

**Required later contract:** A versioned export manifest links canonical product/variant and PI snapshot/pack, claim evidence, selected source asset IDs/origin/digests, dossier/brief/script/storyboard digests, prompt/model versions, START/END keyframe attempt hashes/QC, scene provider kind/operation/attempt/clip hashes, composite probe, all five approvals, final QC and cumulative spend. It uses stable IDs/digests into retained stores rather than dumping raw payloads or trusting caller-supplied facts. Missing links are identified truthfully; changed bytes require a new immutable version. Regression coverage resolves each link from a seeded canonical store and retains existing decode/SHA/QC negative tests. Full master-spec §10.2 compliance is not claimed until this passes.

### FIX-010 — Optional image reacquisition

**Current safe contract:** `qc/image_qc.py:314` can recommend `reacquire_references`; `handlers.py:2015-2039` blocks Product Lock on non-PASS or fewer than two eligible assets. `ProductImageCleaner` is not a configured worker step. This is safe for a product whose initial references pass.

**Conditional future contract:** An operator or governed acquisition action supplies new source identity/bytes; new SHA, containment, identity and Image QC checks are mandatory. Old QC cannot authorize changed references, and Product Lock remains blocked until at least two new/current eligible assets receive an authentic PASS report. Automatic cleaning/reacquisition is not inferred merely from the existence of a helper. Regression coverage uses changed bytes and rejects stale-QC reuse.

### Other deferred or excluded work

- **Full Flow** is deferred only under the Vertex-only decision; truthful Flow unavailability and provider selection are not deferred.
- **Legacy daily importer and forwarding-shim removal** have no verified defect and remain outside this specification. The configured MCP runbook entry point must keep working.
- **Ten-product live throughput or a raised daily cap** is not specified. FIX-011 requires staged fake-provider stress and controlled selected-provider quota evidence before scaling.
- **Production-data migration audit:** No migration defect was demonstrated by the verification; any specific historical row incompatibility found during implementation must be recorded with reproduction before changing schemas beyond each fix's minimum contract.

## 13. Definition of Done

This specification is planning-ready when every FIX-001 through FIX-011 has the explicit disposition in §2; every current fix has the required behavior, state/data/failure/retry/compatibility and tests above; conditional choices remain visible in §11; and no optional recovery feature is treated as a prerequisite without a product decision. It defines no task-by-task implementation order beyond the real dependencies in §7.

**Milestone A is accepted only when** HFX-REQ-001/002/004–012/017–019 and the selected-provider branch HFX-REQ-003 if applicable have passing offline evidence; the exact combined gate is green; one configured live product crosses all five reviewed gates and has authentic PI/model/QC/keyframe/video evidence, inspected scene content, a fully decodable SHA-verified immutable export and safe replay after restart. If full §10.2 metadata is chosen for first signoff, HFX-REQ-023 is also required. A synthetic Flow operation or fake-provider video cannot satisfy this.

**Milestone B is accepted only when** Milestone A remains valid and HFX-REQ-013–016/020–022 have passing multi-worker SQLite/concurrency/restart evidence and the selected provider has a controlled live capacity/quota check. Flow profile exclusivity is required only when Flow is enabled.

**Milestone C is accepted when** the selected deferred requirements HFX-REQ-023–025 pass their stated contracts and full metadata compliance is claimed only after FIX-009. If automatic recovery remains out of scope, fail-closed operator-blocked behavior and a documented manual path are the accepted outcome.

SPEC READY FOR IMPLEMENTATION PLANNING: YES
