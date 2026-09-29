# Hermes Product Video — Fix Implementation Plan

- **Date:** 2026-09-23
- **Status:** Planning only; no production code or tests changed in this pass.
- **Authority:** [Technical Fix Specification](2026-09-23-hermes-product-video-fix-spec.md), [Verified Fix Backlog](2026-09-23-hermes-product-video-verified-fix-backlog.md), [Product Video master spec](../docs/superpowers/specs/product-video-master-spec.md), and current source/tests. Source and executable tests take precedence if a planned step proves inaccurate.

## 1. Objective and release boundaries

Deliver the verified fixes without reopening the architecture refactor. **Milestone A** is one controlled real product using one explicitly selected live render provider and one worker. **Milestone B** is safe concurrent/automated paid work. **Milestone C** is provenance and product-selected recovery. Completion of A never implies B, and passing offline tests never implies live provider acceptance.

This is a task sequence, not authorization to make paid calls, deploy, change production configuration, or remove compatibility paths. Each task names its smallest existing owner, observable completion and test gate. Implementation should use the Hermes Personal architecture governance rule and skill already identified in [the specification](2026-09-23-hermes-product-video-fix-spec.md), keep SQLite and `ProductVideoWorkspaceLayout` as the durable authorities, and preserve five HITL gates, budget admission, relative media paths and immutable artifacts.

**Current baseline:** the completed verification had 1,108 passing and five failing combined tests; the MCP-only rerun for the specification had 34 passing and five failing tests. The five are contract/fixture mismatches as classified in FIX-008. No live provider path has been accepted. The working tree already contains unrelated modifications; every implementation task must inspect and preserve those changes before editing.

## 2. Decisions and prerequisites

The following choices must be recorded before the **dependent** work or acceptance attempt; independent tasks may proceed:

| Decision | Required by | Branch in this plan |
| --- | --- | --- |
| First real provider: **Vertex only** or **Vertex + Google Flow** | T-A1 live acceptance | Vertex-only: make Flow truthfully unavailable, select and verify Vertex. With Flow: execute T-A1F and live Flow reconciliation/profile checks. |
| END policy for a provider without last-frame conditioning | T-A4 | Reject `generated/required` before paid work, or permit an explicitly recorded `omitted` scene policy. Both fix scene/frame identity. |
| First-run export metadata: diagnostic run or full master-spec §10.2 signoff | T-A6 | Diagnostic run defers T-C1. Full signoff moves T-C1 before A acceptance. |
| Initial failed Video QC recovery: manual/operator-blocked or automatic scene regeneration | T-C2 only, unless chosen for A | Current safe block remains. Automatic path activates T-C2. |
| Image failure recovery: manual replacement or automatic reacquisition | T-C3 only, unless chosen for A | Current Image QC block remains. Automatic path activates T-C3. |

No decision is needed to retain strict QC/export checks or prevent duplicate paid submission. A controlled live run also needs a configured provider, credentials/session, one real READY PI product, explicit bounded budget authorization and operator review. The review host's unset `video_factory.render_provider` is setup state; do not create a code ticket for that observation.

### Task T-00 — Establish a reviewable baseline

**Scope:** Before changing code, record the actual diff/status of each target file, configured provider for the test environment, and the existing failing MCP cases. Use a temporary `HERMES_HOME` and temporary SQLite/workspace for any new integration tests. Read the repository architecture rule, governance skill, code/data rules and canonical docs before schema, contract or artifact edits.

**Deliverable:** A short implementation note tying every edit to one FIX/HFX requirement, naming the existing owner and data source of truth. No new parallel repository, workflow, media tree or provider abstraction. Do not use a live paid provider in baseline tests.

**Gate:** Reproduce the five known MCP failures without adding new failures; retain the [specification baseline](2026-09-23-hermes-product-video-fix-spec.md#3-current-verified-baseline) for comparison. This task does not delay independent source-only fixes if the original baseline report is still current.

## 3. Milestone A — Controlled real single-product readiness

### Task T-A1 — FIX-001: make provider selection and readiness truthful

**Requirements:** HFX-REQ-001/002/004; HFX-REQ-003 only for Flow-selected scope.

**Edit boundary:** `hermes_personal/integrations/video_factory/google_flow_provider.py` and the immediate `server.py::_video_provider` selection/readiness path. Confirm `scene_renderer.py::SceneRenderRuntime` already pins provider kind and refuses post-submit fallback; keep that logic. Review `cli-config.yaml.example` and doctor/preflight text so an example cannot imply Flow is ready merely because Playwright imports. Credentials remain in the credential mechanism; non-secret selection in `config.yaml`.

**Work:** Define and test the actual readiness prerequisites of the configured adapter. The default Flow construction currently supplies no page/session; it must report unavailable and cannot invent `gflow_op_*` as accepted work. Missing provider selection must yield a clear pre-submission setup result. For Vertex-only scope, ensure selection contains only Vertex or explicitly disables pre-submit fallback to Flow. Existing durable `provider_kind` and external operation ID remain the resume authority; synthetic historical Flow IDs are marked ambiguous for operator reconciliation.

**Conditional T-A1F (Flow selected):** Wire the existing Flow adapter to an authenticated, exclusively owned browser context; submit through the real UI; record externally verifiable operation identity; poll/download a real clip; reconcile the same request after a new process. Resolve profile ownership jointly with T-B3 before claiming concurrent Flow use. Do not invent a second provider framework or represent an unknown ID as `running`.

**Tests:** Extend `tests/hermes_personal/product_video/test_render_provider_selection.py` for installed Playwright/no session, selected Vertex/no Flow fallback, provider pin after restart and ambiguous Flow ID. Provider contract tests cover Flow submit/poll/lookup only if selected. The selected provider must eventually pass one controlled live clip; fake provider tests alone end at OFFLINE VERIFIED.

**Done when:** HFX-AT-001/002/004 pass; HFX-AT-003 passes only for the Flow branch. No paid call occurs on unavailable/unconfigured selection.

### Task T-A2 — FIX-002: establish the VF storyboard write boundary

**Requirements:** HFX-REQ-005/006.

**Edit boundary:** `hermes_personal/product_video/handlers.py` at the approved Scene Plan → storyboard handoff and, if needed, `product_video/mcp_adapters.py::create_storyboard`. The configured adapter dispatches the VF tool; `integrations/video_factory/client.py` is a deterministic local request wrapper and is not the configured persistence path. The VF tool at `integrations/video_factory/server.py::create_storyboard` already returns `ok`, `project_id`, `storyboard_id` and frames.

**Work:** Stop swallowing both exceptions and unsuccessful return values. Confirm `ok`, owner/project, approved scene-plan binding and expected scene IDs from the canonical write/read before compiling keyframe requests. Keep the workflow at the failed boundary with an explicit VF error; neither paid keyframe submission nor a Storyboard gate candidate may occur. On lost acknowledgement, retry with the same idempotency identity and read back the canonical storyboard; continue only if it matches, otherwise report conflict.

**Tests:** Add fault-injection cases for exception, `ok=false`, wrong project/scene IDs and lost acknowledgement to `test_creative_handler_wiring.py` or a focused handler test. Add a real SQLite VF write/read-back workflow test with failed-then-successful outbox delivery. Assert provider submit count zero before confirmed persistence and one matching storyboard after retry.

**Done when:** HFX-AT-005–007 pass; the existing successful keyframe/Storyboard gate test remains green.

### Task T-A3 — FIX-003: correct PI claim and source mapping

**Requirements:** HFX-REQ-007–009.

**Edit boundary:** `hermes_personal/product_video/handlers.py::_locked_research_dossier`; validate the configured PI adapter payload in `product_video/mcp_adapters.py` only if it loses a needed existing claim/source field. Retain `creative/dossier.py`, V2 contracts and the persisted PI snapshot/pack as canonical owners.

**Work:** Build each dossier claim from its own PI claim ID, text, support status and evidence/source references. Drop the shared pack-wide `supporting_evidence_ids` assignment and `mi.com` official-source assumption. Use the locked product/variant and PI source classification or a validated vendor-neutral rule. Exclude or block claims whose relationships cannot be resolved; do not mint “supported” status. If the configured PI service lacks claim-level evidence, expose the narrow PI wire-contract gap and block factual creative use rather than creating a new evidence store.

**Tests:** Add two-claim/two-evidence, unsupported-claim, unknown/cross-product evidence and non-Xiaomi official-source fixtures. Extend `test_research_dossier.py` and `test_pi_mcp_contract.py` with persisted snapshot/pack → dossier → brief/script claim-reference assertions. Confirm same locked inputs produce the same dossier digest and missing grounding blocks paid creative generation.

**Done when:** HFX-AT-008–010 pass, and the chosen live product's actual PI claim/evidence relationships can be inspected at the Creative Direction gate.

### Task T-A4 — FIX-004: join START and END frames to one scene

**Requirements:** HFX-REQ-010–012. Record the END policy decision before enabling paid generation of a scene requesting `generated` or `required`.

**Edit boundary:** `product_video/handlers.py` generated-keyframe packaging; `integrations/video_factory/server.py::render` package/frame mapping; `integrations/video_factory/ports.py::VideoGenerationRequest` and `scene_renderer.py` normalized request/digest. Provider adapters change only if the selected adapter can actually consume an END frame. Keep the existing V2 `creative/storyboard.py` scene plan and keyframe QC package.

**Work:** Store the approved scene ID directly for both roles; keep distinct `frame_id` and `frame_role`. Validate a `(scene_id, role)` frame set but count scenes by scene ID. Require one START and at most one END for each scene. Represent END as an optional provider-neutral role-tagged input with exact path/SHA/QC/package binding; start-only callers retain their current shape. Include the END binding or explicit omission policy in the request digest/operation identity. Expose a narrow, explicit END-conditioning capability at the selected provider edge, defaulting to unsupported until its adapter contract proves support. Check it **before** paid keyframe/video work; reject unsupported `generated/required` or use a product-approved `omitted` policy with reason. Preserve QC and approval invalidation on changed END bytes.

**Tests:** Extend `test_storyboard_compiler.py`, `test_remediation_adversarial.py`, `test_scene_render_runtime.py` and a focused server render integration: one scene with two frames yields one render request; both hashes/QC validated; unsupported policy submits nothing; changed END invalidates clip/composite/QC/Final approval. If a provider claims END support, assert its adapter transmits a distinct last-frame input and inspect a live conditioned scene before making that claim.

**Done when:** HFX-AT-011–013 pass. A start-only run remains compatible and no END is silently ignored.

### Task T-A5 — FIX-008: reconcile the MCP contract gate

**Requirements:** HFX-REQ-017–019. This task is independent of A1–A3 and may be done early; adjust the positive render fixture to the final A4 package contract if A4 changes that contract.

**Edit boundary:** Only the five named cases in `tests/mcp_servers/test_video_factory_server.py` and `tests/mcp_servers/test_video_factory_paid_contract.py`, plus direct-caller fixtures/docs if the audit proves they need updating. Do not weaken `server.py::render/export` lineage, keyframe QC, Final approval, Video QC or media validation for fixture convenience.

**Work:** For each failing negative case, supply earlier required lineage when testing a later guard or assert the actual earliest fail-closed error. For the positive render case, create the current approved V2 generated-keyframe/QC package instead of a symbolic listing reference. For positive export, include the canonical SHA and artifact identity, authentic approval and exact SQLite PASS Video QC bound to decodable MP4 bytes. Preserve deterministic same-version replay assertions. Audit configured direct MCP callers separately; record any real caller regression with its own reproduction instead of silently labeling it a stale test.

**Five exact cases:** `test_render_and_export_fail_closed_truthfully`, `test_render_submits_approved_storyboard_to_provider`, `test_deterministic_export_promotes_mp4_without_provider_call`, `test_export_fails_when_caption_identity_is_pack_id_or_generic`, and `test_export_fails_without_valid_project_and_final_approval`. Their present classification and expected contract are in [FIX-008 of the spec](2026-09-23-hermes-product-video-fix-spec.md#fix-008--reconcile-the-five-mcp-tests-with-the-strict-contract).

**Tests:** First run both MCP files; then the exact combined command in §6. Keep explicit negative tests for missing lineage, absent/stale keyframe QC, unapproved storyboard, wrong owner/project, invalid MP4 bytes, stale Video QC and wrong SHA.

**Done when:** HFX-AT-020–022 pass and the combined gate has zero failures without relaxed production checks.

### Task T-A6 — integrate, preflight and run one controlled real product

**Dependency:** T-A1–A5, all Milestone A decisions that affect the selected run, and T-C1 if full §10.2 metadata is part of first-run signoff. This is an acceptance task, not another feature ticket.

**Offline gate:** Run focused tests as each boundary changes, then `uv run ruff check hermes_personal tests/hermes_personal tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py` and `uv run pytest tests/hermes_personal tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py -q`. The latter must be green. Use a temporary home/SQLite path for non-live tests, preserve no-network fake-provider fixtures and verify restart/replay.

**Live gate:** Follow `docs/superpowers/plans/product-video-master-plan.md` Task 10 and the Product Video runbook: doctor/preflight, backup exact SQLite files, one bounded reusable budget authorization, one READY PI product/variant, selected authenticated live providers and operator review at Product Lock, Brief, Scene Plan, Storyboard and Final. Inspect each scene of the produced MP4 and record authentic PI/claim refs, prompt/model versions, keyframe/scene operation IDs, QC report IDs, approval IDs, final decode/probe/SHA and actual/unknown spend. Restart the worker and prove accepted operation IDs are polled/reused rather than resubmitted.

**Failure rule:** Any missing provider, ambiguous paid operation, ungrounded claim, absent storyboard, unsupported END policy, non-PASS QC, stale approval, invalid video or red combined gate is a **NO-GO** for Milestone A. Preserve artifacts and operation records; do not substitute a mock result to claim success.

**Done when:** The evidence satisfies the spec's **CONTROLLED SINGLE-PRODUCT E2E VERIFIED** level. Record exactly which provider was live verified. A live Vertex run never certifies Flow.

## 4. Milestone B — Concurrent and automated paid production

T-B1 and T-B2 address different races and may be developed independently. T-B3 must be validated against both. None should be treated as a substitute for Milestone A's live content/evidence checks.

### Task T-B1 — FIX-005: atomic first keyframe submit

**Requirements:** HFX-REQ-013/014.

**Edit boundary:** `integrations/video_factory/keyframe_provider.py::KeyframeOperationStore/KeyframeRuntime`. Reuse the existing SQLite operation row, request digest and the `BEGIN IMMEDIATE`/conditional-claim pattern already used by `scene_renderer.py::SceneRenderOperationStore.claim_provider_for_submission`. Do not introduce a second queue or distributed lock.

**Work:** Make the absent/planned → claimed/submitting checkpoint an atomic winner operation committed before `provider.submit`. Losing workers read the winner's row and poll/wait/reconcile; they never submit. Persist provider operation identity when available. Preserve exact completed-file SHA reuse and digest conflict. An ambiguous crash after claim and before external ID remains `RECONCILIATION_REQUIRED`. A terminal failed attempt does not automatically resubmit under the same identity: require a distinct authorized attempt or verified proof the provider did not accept/charge the first call. Audit the existing `test_runtime_retries_terminal_provider_failure` expectation; change it to the new bounded attempt contract rather than retaining unsafe same-ID resubmission.

**Data impact:** Prefer a conditional claim over the current upsert overwrite. Add only the minimum claim/attempt metadata if existing row status cannot express winner and ambiguity safely. Any SQLite migration must preserve completed and unknown historical rows.

**Tests:** Two SQLite connections released simultaneously on one operation, fake provider call counter exactly one; same ID/different digest conflict; crash at each boundary before/after provider ID; replay completed artifact with correct/changed SHA; new authorized retry attempt uses a distinct identity. Use real SQLite transactions, not only a mocked store.

**Done when:** HFX-AT-014–016 pass and the existing operator-authorized keyframe regeneration/QC path still works.

### Task T-B2 — FIX-006: protect VF project writes

**Requirements:** HFX-REQ-015/016.

**Edit boundary:** `integrations/video_factory/domain.py::VideoFactoryProject`, `repository.py::SQLiteVideoFactoryRepository`, and direct `service.py` callers. Current `repository.save` writes almost every project column under owner/project only; semantic per-artifact versions do not cover every row mutation. Use the existing VF repository as owner.

**Work:** Choose one reliable conditional-write contract before editing: a monotonic project revision carried on read/save is the smallest likely solution; a targeted field update is acceptable only if it prevents the same lost-update class across storyboard, scenes, timeline and approvals. If revision is chosen, add an additive SQLite column/default/backfill, include it in `VideoFactoryProject`, save with `WHERE id/owner/revision` and increment atomically; a zero-row save returns explicit conflict, never success. Audit every `service.py` save path so it either propagates conflict or rereads/revalidates the intended update; no blind retry with stale approval/QC. Existing serialized projects and immutable exports remain valid.

**Tests:** Real SQLite stale-reader interleaving: writer A changes one field, writer B changes another from the old snapshot; B conflicts or safely merges, and A's committed value remains. Cover same-project scene/approval paths, wrong owner, identical replay, different-project independence, restart against a historical row and sequential happy path. Keep render/composite/export regression tests.

**Done when:** HFX-AT-017–019 pass. No concurrent valid update is silently lost.

### Task T-B3 — FIX-011: shared provider capacity and Flow profile ownership

**Requirements:** HFX-REQ-020 (Flow only), HFX-REQ-021/022.

**Dependency:** T-B1 and T-B2 for concurrent paid acceptance; T-A1F when Flow is enabled. Capacity control does not repair duplicate keyframe claims or VF lost updates.

**Edit boundary:** Paid-call admission at `KeyframeRuntime.run` and `SceneRenderRuntime.run` or their existing shared immediate caller; specialized durable ownership within existing SQLite-backed Video Factory infrastructure. `google_flow_provider.py` owns profile use if enabled. `config.yaml` owns non-secret capacity/profile policy, while credentials remain secret.

**Work:** Define per-provider in-flight limit and durable slot acquisition/release across workers. Queue excess eligible work in the existing durable job state without a provider call. Tie slot ownership to one logical operation and a recoverable worker lease; on expiry, reconcile possibly accepted work before another paid call. For Flow, one authenticated browser profile has one active owner. Keep selected provider pins, budget reservations and outbox delivery identities stable while waiting. Use the existing SQLite/lease design; do not add RabbitMQ, Kafka, Redis, DLQ or a second coordinator.

**Tests:** Two or more worker connections with a configured capacity N never exceed N counted provider calls in flight; busy Flow profile never has two active owners; worker death and lease expiry resume queued work without duplicate operation IDs or spend; rate limit/timeout retains one pinned operation. Run the existing three-product offline smoke and staged ten-product fake-provider stress across batches, without raising the present three-product batch cap.

**Done when:** HFX-AT-023–025 pass for enabled scope. A separate controlled live quota/profile exercise is still needed before declaring CONCURRENT PRODUCTION VERIFIED.

### Task T-B4 — concurrent production acceptance

**Offline gate:** Rerun targeted concurrency/restart tests for T-B1–B3, `uv run pytest tests/hermes_personal -q`, the combined MCP/Product Video command from T-A6, and Ruff. Prove same-project conflict safety, cross-product path isolation, operation-ID uniqueness and no budget double charge under duplicate delivery. Preserve final export/approval tests.

**Live gate:** With the already accepted Milestone A provider and bounded authorization, exercise only an approved small concurrent workload inside configured provider capacity. Capture actual in-flight count, external operation identities, rate-limit behavior, worker restart reconciliation and Flow profile lease evidence if Flow is enabled. No claim of ten-product paid throughput is required.

**Done when:** The evidence satisfies the spec's **CONCURRENT PRODUCTION VERIFIED** level. If the provider's real quota/session behavior is unavailable, retain OFFLINE VERIFIED for the concurrency mechanism and defer the production claim.

## 5. Milestone C — provenance and optional recovery

### Task T-C1 — FIX-009: complete export provenance

**Requirements:** HFX-REQ-023. Run before Milestone A signoff only if the §11 metadata decision requires full master-spec §10.2 fields at first acceptance; otherwise run after the initial real video and before claiming full master-spec compliance.

**Edit boundary:** Existing `integrations/video_factory/server.py::export` provenance assembly, `export_package.py` metadata, and `product_video/mcp_adapters.py` reference mirroring only where it loses canonical origin. Read from current PI/WF/VF/QC/operation stores; do not make caller-supplied metadata authoritative or add a parallel export database.

**Work:** Add versioned canonical IDs/digests for product/variant, PI snapshot/pack and claim evidence, source asset/origin, dossier/brief/script/storyboard and prompt/model versions, keyframe attempt/QC, scene provider kind/operation/attempt/clip, five approvals, composite probe/final Video QC and cumulative spend. Link to retained records rather than copy full raw payloads. Mark truly unavailable historical fields honestly; do not fabricate them. Preserve same-version immutable replay, exact SHA/full decode and approval/QC checks.

**Tests:** Seed canonical stores and resolve each manifest link back to exact records/files; verify parent/digest consistency, same-version idempotence, missing link behavior and changed-byte versioning. Retain `test_export_integrity.py`, `test_export_package.py` and MCP negative export cases.

**Done when:** The produced `metadata.json` answers the minimum provenance questions in FIX-009 and master-spec §10.2 without weakening export integrity. A real exported product is inspected for link completeness before full spec signoff.

### Task T-C2 — FIX-007: optional governed Video QC scene recovery

**Activation:** Only if the product decision requires automatic scene regeneration. Otherwise document the current safe `WaitingForOperator` state and manual correction path; do not add an automatic action.

**Edit boundary if activated:** `product_video/qc/video_qc.py` recommendation contract, operator command/handler, Product Video workflow state and existing VF scene-operation/render-batch/composition path. Keep old failed clips/QC in immutable attempt lineage.

**Work if activated:** Bind a selected `retry_scene_N` finding to the current scene/QC artifact and explicit operator authorization, attempt number and budget. Enforce a finite retry cap. Create a new scene attempt, invalidate composite/Video QC/Final approval, regenerate only that scene, recompose and demand fresh PASS QC before Final eligibility. Replay cannot charge twice. No automatic unlimited retry loop.

**Tests if activated:** FAIL → operator-authorized retry → new scene clip → new composite → fresh QC → Final eligibility; rejection for missing authorization, exhausted attempts, stale QC, duplicate delivery and old approval reuse. Keep the present non-PASS export block test.

**Done when:** Either a documented manual path is accepted, or the conditional action meets the spec without weakening fail-closed QC.

### Task T-C3 — FIX-010: optional image reacquisition

**Activation:** Only if the product decision requires automatic source replacement. Manual source replacement with fresh QC is sufficient for a controlled product whose input set can be corrected by an operator.

**Edit boundary if activated:** Existing source ingestion, `product_video/qc/image_qc.py`, Product Lock transition and `ProductVideoWorkspaceLayout`. `ProductImageCleaner` is not adopted merely because its unit tests pass.

**Work if activated:** Treat any replacement/cleaned image as new immutable source bytes with asset ID, SHA, containment, source lineage and new Image QC. Keep originals. Product Lock remains unavailable until at least two eligible assets in a current authentic PASS report. Preserve previous failed QC and do not reuse it for changed bytes.

**Tests if activated:** Bad/insufficient source set blocks; replacement asset changes hash/identity and demands new QC; stale report cannot authorize Product Lock; path traversal and owner mismatch remain rejected.

**Done when:** Manual or automated path has explicit safe behavior. Automatic reacquisition is not a precondition for Milestone A unless explicitly selected.

## 6. Dependency order and change boundaries

```text
Provider decision ──→ T-A1 readiness ──→ selected live-provider evidence ──→ T-A6
T-A2 VF storyboard ──→ keyframe/gate integration in T-A6
T-A3 grounded PI ──→ trustworthy creative review in T-A6 ──→ T-C1 claim lineage
End-frame policy ──→ T-A4 package/capability contract ──→ render acceptance in T-A6
T-A5 MCP contract gate ───────────────────────────────────────→ formal T-A6 signoff
T-A6 single-product acceptance ──→ live concurrent acceptance T-B4
T-B1 keyframe claim + T-B2 VF conflict ──→ T-B3 capacity ──→ T-B4
Metadata decision ──→ T-C1 before A signoff OR after initial A diagnostic run
Video QC/image decisions ──→ T-C2/T-C3 only if activated
```

T-A1 readiness, T-A2 storyboard, T-A3 PI mapping and the stale-test portion of T-A5 can proceed independently. T-A4 needs the END policy before enabling an unsupported provider branch, but scene/frame identity tests can proceed without that choice. T-B1 and T-B2 are independent defects. No task includes moving modules, removing old import shims, changing the five gates, adding a new provider family, increasing the daily product cap or changing export bytes without a version.

Before any schema or artifact change, the implementer must identify the existing owner, SQLite source of truth, contract version, compatibility path, parent IDs/digests, QC/approval binding and restart test. Any need for a parallel owner, absolute persisted path, new queue/broker or irreversible cleanup stops the task for design reconciliation under the Hermes Personal governance rule.

## 7. Verification commands and evidence

Run the narrowest applicable test after each boundary, then the milestone gates. Exact proposed commands on native Windows:

```powershell
uv run pytest tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py -q --tb=short
uv run pytest tests/hermes_personal/product_video/test_render_provider_selection.py tests/hermes_personal/product_video/test_creative_handler_wiring.py tests/hermes_personal/product_video/test_research_dossier.py tests/hermes_personal/product_video/test_pi_mcp_contract.py tests/hermes_personal/product_video/test_storyboard_compiler.py tests/hermes_personal/product_video/test_scene_render_runtime.py tests/hermes_personal/product_video/test_keyframe_pipeline.py -q
uv run pytest tests/hermes_personal -q
uv run pytest tests/hermes_personal tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py -q
uv run ruff check hermes_personal tests/hermes_personal tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py
```

Run `scripts/run_tests.sh` from a supported shell before an upstream PR as required by `AGENTS.md`. New tests should assert behavior relationships and interleavings rather than snapshots of enum counts/config versions. Use real imports, temporary SQLite and workspace paths, separate connections for concurrency, and actual decodable local fixtures for export. External provider calls belong only to the controlled live acceptance with explicit authorization and recorded spend.

For each milestone attach a compact evidence record: selected provider/config scope, test command/result, source revision, operator approval IDs, workflow/project/artifact IDs, operation IDs, QC report IDs, media SHA/probe, spend, restart result and unresolved limitations. Do not place credentials in logs or reports. A red gate or unavailable provider remains a reported blocker, not a reason to weaken a guard.

## 8. Task-to-requirement traceability

| Task | FIX | HFX requirements | Primary completion evidence |
| --- | --- | --- | --- |
| T-A1 / conditional T-A1F | 001 | 001–004 | Readiness/selection/pin tests; selected-provider live clip |
| T-A2 | 002 | 005–006 | VF fault/retry workflow with zero pre-write keyframe submits |
| T-A3 | 003 | 007–009 | Distinct PI evidence/source mapping and live product review |
| T-A4 | 004 | 010–012 | Two-frame one-scene package, capability gate, invalidation |
| T-A5 | 008 | 017–019 | Five MCP cases green, combined gate green, direct-caller audit |
| T-A6 | Acceptance | A requirements | Real five-gate inspected Product Video and safe replay |
| T-B1 | 005 | 013–014 | Two-worker one-submit and crash/restart evidence |
| T-B2 | 006 | 015–016 | VF stale-reader conflict/merge and historical-row evidence |
| T-B3 | 011 | 020–022 | Shared capacity/profile tests and staged stress |
| T-B4 | Acceptance | B requirements | Controlled concurrent provider/quota evidence |
| T-C1 | 009 | 023 | Canonical export metadata link resolution |
| T-C2 if selected | 007 | 024 | Authorized bounded Video QC scene correction |
| T-C3 if selected | 010 | 025 | New-source Image QC and stale-QC rejection |

## 9. Exit criteria and handoff

The implementation phase can begin with T-A1 readiness, T-A2, T-A3, T-A5 and the unconditional scene/frame portion of T-A4 while the product decisions are recorded. A task is complete only with its exact HFX acceptance evidence and preserved non-regression checks. Milestone A, B and C exit independently under the [technical specification](2026-09-23-hermes-product-video-fix-spec.md#13-definition-of-done).

**Current execution status:** This plan is complete; no fix has been implemented here. The combined regression gate remains known-red from five MCP cases, and live acceptance remains unperformed. The first implementation change must preserve the existing dirty working tree and should be reviewed as a narrow FIX-scoped change.
