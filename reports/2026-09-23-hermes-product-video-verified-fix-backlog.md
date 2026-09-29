# Hermes Product Video — Verified Fix Backlog

**Date:** 2026-09-23  
**Input of record:** [Post-refactor feature and runtime verification](2026-09-23-hermes-product-video-post-refactor-verification.md). Source/test references below resolve disputed scope; this is a fix backlog, **not** a technical design or implementation plan. No production code was modified.

Priority rule: **P0** only for an enabled/default behavior that is unusable, loses data, or takes an unsafe irreversible action; **P1** required before controlled real acceptance or ordinary production; **P2** important hardening/recovery after first acceptance; **P3** optional or cleanup. “Blocks single-product E2E” means the affected current behavior can prevent a valid controlled run or invalidate its acceptance, not that every offline happy-path test fails. Conditional priorities are explicit.

## 1. Current Readiness Summary

The offline provider-substituted Product Video workflow reaches all five operator gates and produces a validated export. Atomic intake claims, persisted workflow/outbox state, PI snapshot prerequisites, structured V2 creative outputs, image/keyframe/video QC, durable scene operations, composition, and exact approval/QC/decode/SHA export checks have passing tests. The combined verification run produced **1,108 passed / 5 failed**; all five failures are older MCP render/export tests whose fixtures or expected error codes conflict with the current strict contract. A focused offline flow run passed **51 tests**. No paid or live PI/model/evaluator/Vertex/Flow end-to-end run was performed.

One controlled real run is **not ready for formal acceptance**. The example configuration selects Google Flow, whose default adapter does not drive an authenticated browser or persist a real operation (`cli-config.yaml.example:1933-1936`; `google_flow_provider.py:56-173`). On this review host, read-only `load_config()` returned **no selected `video_factory.render_provider`**, so operator configuration is also a prerequisite; this is a deployment state, not a code defect. If Vertex is selected and Flow is explicitly unavailable, full Flow implementation can be deferred, but provider readiness must be truthful. Claim evidence mapping, VF storyboard write handling, and the end-frame branch can invalidate a real run. The red MCP test gate must be resolved before claiming acceptance.

**Safe scope today:** offline/single-worker verification with substituted providers, and controlled local use that preserves the five gates. Do not claim live provider readiness or concurrent paid production. The configured single-product path should be taken live only after the first priority group and explicit provider selection; concurrent/multi-product live use requires the second group.

## 2. Confirmed Issues

### FIX-001 — Truthful render-provider readiness and Google Flow operation

**Category:** Real E2E blocker / runtime wiring.  
**Priority:** **P1** for truthful readiness/selection before any real run; **P0 conditional** if Google Flow is enabled for that run, because its current default operation cannot complete. Full Flow browser support can move to **P3/optional** for the first acceptance if Vertex alone is selected and Flow is disabled.  
**Type:** BUG / DEFECT in enabled Flow behavior; configuration/readiness defect.  
**Affected flow:** Approved Storyboard → provider selection → scene submit/poll/restart → clip.  
**Blocks single-product E2E:** **YES** for Flow-selected runs; **NO** for a properly selected, live-verified Vertex run.  
**Blocks concurrent production:** **YES** for Flow; profile/session ownership is absent.

**Expected behavior:** A provider is marked ready only when its required session/credentials and job-submission/polling dependencies are usable. A selected Flow request must create a real externally identifiable job, resume/poll it after restart, and return an actual validated clip or a durable terminal failure. An unavailable Flow edge must fail before paid scene submission; provider pinning must remain stable.

**Actual behavior:** `_video_provider()` constructs `GoogleFlowPlaywrightProvider.from_config(output_dir=ws)` without a page/session (`integrations/video_factory/server.py:1749-1758`). `is_available()` accepts an importable Playwright package; `submit()` invents `gflow_op_<request-id>` and stores `submitted` only in memory; fresh-process lookup returns `None`, while polling returns `running` without a real job (`google_flow_provider.py:56-173`). Read-only verification reproduced `submitted → submitted` in one instance and `lookup=None`, `poll=running` after a new instance. The example config selects Flow; current local resolved provider was unset.

**Evidence:** Source: `integrations/video_factory/server.py:1749-1758`, `integrations/video_factory/google_flow_provider.py:56-173`, `cli-config.yaml.example:1933-1936`. Runtime: the read-only restart probe above; no live Flow job was run (verification report §11/§15).

**Impact:** A Flow-selected product may spend workflow time waiting on an operation that never generated media, and restart cannot reconcile it. A successful mock does not establish live readiness.

**Required outcome:** For initial Vertex-only acceptance, Flow is unselectable/unready and provider selection reports that fact clearly. If Flow is part of the selected production scope, its browser authentication, submission, operation identity, polling, restart lookup and profile ownership must actually work.

**Smallest correct scope:** Correct readiness and provider selection for the chosen run; implement and verify the Flow adapter only if Flow is enabled.

**Acceptance criteria:**

- With no authenticated/usable Flow session, readiness is false and no scene operation is reported submitted or paid.
- Vertex selection never silently falls back to Flow, and a pinned provider never changes on resume.
- If Flow is enabled, a submitted request has an externally verifiable operation ID; after process restart, the same request is found/polled to a real decodable clip or terminal failure.
- One controlled live clip is observed **only if Flow is selected**; offline contract tests alone do not label it production-verified.

**Regression coverage:** Unit/provider-contract tests for missing browser prerequisites and normalized failure; integration/restart test with a controlled browser adapter; selection/pin test with Vertex; live provider acceptance only for the provider actually enabled.  
**Dependencies:** Provider decision in §6; readiness precedes live provider acceptance. No dependency on QC recovery or export enrichment.  
**Out of scope:** New render-provider families, synthetic slideshow fallback, broad provider abstraction changes, and forcing Flow implementation when Vertex-only acceptance is chosen.

### FIX-002 — Do not advance after Video Factory storyboard write failure

**Category:** Correctness / cross-store handoff.  
**Priority:** **P1**.  
**Type:** BUG / DEFECT.  
**Affected flow:** Approved Scene Plan → VF storyboard persistence → keyframes/QC → Storyboard gate → render.  
**Blocks single-product E2E:** **YES** when the VF write fails.  
**Blocks concurrent production:** **YES**; failure is harder to reconcile under parallel work.

**Expected behavior:** The workflow must not create paid keyframe work or a Storyboard approval candidate until the canonical VF storyboard write succeeds for the same project and approved scene plan.

**Actual behavior:** The configured keyframe branch calls `video_client.create_storyboard()` under `except Exception: pass`, then continues to compile and generate keyframes (`product_video/handlers.py:1283-1315`). Render later requires `project.storyboard` and approved VF frames (`integrations/video_factory/server.py:1917-1931`).

**Evidence:** Source: `product_video/handlers.py:1283-1315`, `integrations/video_factory/server.py:1917-1931`. Tests: offline happy-path coverage passes but does not inject this VF write failure (verification report §6/§16); the fail-open path is explicit in source.

**Impact:** Workflow and VF can disagree; operator may approve media whose render prerequisite is absent, with paid work already performed.

**Required outcome:** A failed VF write remains a visible job failure with no downstream generation or gate; a retry can establish the same intended storyboard without duplicating completed work.

**Smallest correct scope:** Fail and retry at this handoff; retain the existing VF storyboard and workflow contracts.

**Acceptance criteria:**

- Injected VF storyboard persistence failure leaves the workflow before the Storyboard gate; no keyframe provider submission occurs.
- Failure reason identifies the VF operation/project, and a later successful retry reaches the same scene IDs with one canonical VF storyboard.
- Successful existing start-frame flow and five approval gates continue unchanged.

**Regression coverage:** Handler unit fault injection plus workflow/outbox integration with failed-then-successful VF write; assert no paid keyframe call on first failure.  
**Dependencies:** None for the fail-closed behavior; required before interpreting keyframe and render acceptance.  
**Out of scope:** Moving the handler/VF modules or adding a new distributed transaction framework.

### FIX-003 — Preserve claim-specific PI evidence into the creative dossier

**Category:** Correctness / grounding.  
**Priority:** **P1**.  
**Type:** BUG / DEFECT.  
**Affected flow:** PI ResearchSnapshot → ResourcePack → locked ResearchDossier → brief/script/product claims.  
**Blocks single-product E2E:** **YES** for trustworthy grounded-content acceptance.  
**Blocks concurrent production:** **NO** specifically; the mapping is wrong even for one product.

**Expected behavior:** Each claim retains only its own valid evidence/source relationships and status. Official-source recognition follows the locked product/source data, independent of a hard-coded vendor. Unsupported or untraceable claims cannot be relabeled supported.

**Actual behavior:** `_locked_research_dossier()` filters official URLs with `host.endswith('mi.com')`, takes one pack-wide `supporting_evidence_ids` sequence, attaches it to every claim, labels each `supported`, and builds a synthetic snapshot dict (`product_video/handlers.py:315-359`). The PI adapter otherwise requires a persisted snapshot and pack (`product_video/mcp_adapters.py:264-393`).

**Evidence:** Source: `product_video/handlers.py:315-359`, `product_video/mcp_adapters.py:264-393`. Tests: existing PI persistence/gate tests pass, but do not prove distinct claim mappings across vendors (verification report §4/§16); no live PI grounding acceptance was run.

**Impact:** Non-Xiaomi products can lose official sources and unsupported product facts can appear grounded. This taints creative quality evaluation and export lineage.

**Required outcome:** The locked dossier’s claim IDs, text, support status and evidence references faithfully represent the persisted PI snapshot/pack for that product; missing or mismatched evidence blocks or excludes the claim.

**Smallest correct scope:** Correct the PI pack-to-dossier mapping and its contract tests; preserve the persisted snapshot/pack and V2 creative APIs.

**Acceptance criteria:**

- Two claims with different evidence retain distinct relationships; neither receives the other claim’s evidence.
- A non-Xiaomi product retains its actual official sources; no vendor-specific host is required.
- Unknown/cross-product evidence IDs cannot turn a claim into `supported`; dossier construction reports the reason.
- Brief/script generation consumes the corrected dossier without changing V2 output contracts or the Product Lock gate.

**Regression coverage:** Dossier unit tests with at least two claims, multiple vendors and unknown evidence; PI-adapter-to-creative workflow integration with persisted snapshot/pack fixture. A live PI run is needed for eventual acceptance, but not to prove this mapping fix.  
**Dependencies:** Before judging real creative/model output; logically before export lineage FIX-009.  
**Out of scope:** Rewriting Product Intelligence, changing model prompts wholesale, or introducing a new product-facts database.

### FIX-004 — Keep optional end keyframes within their scene

**Category:** Correctness / feature handoff.  
**Priority:** **P1** for the unconstrained configured V2 flow; conditional **P2** only if the first controlled run explicitly permits and validates omitted end frames and rejects unsupported end-frame policies **before** paid keyframe generation.  
**Type:** BUG / DEFECT for scenes requesting `generated`/`required`.  
**Affected flow:** ScenePlan → start/end keyframe requests → storyboard package/QC → video render request.  
**Blocks single-product E2E:** **YES** when a scene requests an end frame.  
**Blocks concurrent production:** **NO** specifically.

**Expected behavior:** Start and end frames belong to one stable scene ID and have distinct frame roles. An approved required end frame is either used by a capable video provider or rejected as a capability mismatch before paid generation/approval; it must not be silently ignored or counted as a new scene.

**Actual behavior:** `compile_keyframe_requests()` legitimately creates a `scene-id-end` frame (`creative/storyboard.py:270-305`). The handler derives its `scene_id` by removing only `-start`, leaving `scene-id-end` (`product_video/handlers.py:1315-1324`). VF render maps generated frames by this field, requires frame-map size equal to scene count and rejects a one-scene start+end package (`integrations/video_factory/server.py:2104-2140`). The normalized video request includes only the start frame (`scene_renderer.py:241-250`). Existing test covers request construction, not package→render (`test_remediation_adversarial.py:426-487`).

**Evidence:** Source: the four production locations cited above. Test: `tests/hermes_personal/test_remediation_adversarial.py:426-487` covers request compilation but not the render handoff; verification report §8 traces the count mismatch. No live end-frame provider run was performed.

**Impact:** A valid model decision can block rendering after keyframe generation/QC and waste paid work; the end frame cannot constrain the video.

**Required outcome:** One scene remains one scene throughout package validation and render; end-frame policy is applied honestly against provider capability.

**Smallest correct scope:** Preserve scene identity and frame role through packaging and enforce the selected provider policy at the existing handoff.

**Acceptance criteria:**

- A scene with start+end frames yields one scene in the render batch and passes package validation when both frames and QC are valid.
- The provider request uses the approved end frame if supported; otherwise the workflow returns a clear pre-submission capability error or accepts a documented omission policy.
- A changed end-frame SHA invalidates its QC/render relationship just as a changed start frame does.

**Regression coverage:** Contract/unit test for scene/frame identity; workflow integration from V2 scene through two keyframes and QC to render request; provider-capability test with and without end-frame support. Paid/live provider test only if that provider claims end-frame conditioning.  
**Dependencies:** Provider capability decision affects the final acceptance condition; independent of FIX-005 concurrency.  
**Out of scope:** Replanning the creative scene model or forcing every scene to generate an end frame.

### FIX-005 — Single owner for the first paid keyframe submission

**Category:** Concurrency / idempotency.  
**Priority:** **P1 before concurrent or automated paid production**; not a blocker for an isolated single-worker acceptance run.  
**Type:** HARDENING of an unsafe concurrent boundary.  
**Affected flow:** Keyframe operation lookup/checkpoint → provider submit → result persistence/restart.  
**Blocks single-product E2E:** **NO** with one worker.  
**Blocks concurrent production:** **YES**.

**Expected behavior:** For one logical keyframe operation, only one worker may own the first paid submission. Others observe the same durable result or wait/reconcile; a crash cannot cause blind duplicate submission.

**Actual behavior:** `KeyframeRuntime.run()` reads the store, writes an `unknown` checkpoint, then calls `provider.submit()` without an atomic claim that excludes a second worker (`integrations/video_factory/keyframe_provider.py:310-353`). No existing test exercises two concurrent first submissions (verification report §7/§16).

**Evidence:** Source: `integrations/video_factory/keyframe_provider.py:310-353`. Tests: restart/idempotency behavior has passing sequential coverage, while a simultaneous two-worker first-submit case is absent (verification report §7/§16); duplicate paid calls are a source-supported race, not a live observed charge.

**Impact:** Duplicate paid image generations, conflicting outputs and uncertain spend/lineage when multiple workers handle one scene.

**Required outcome:** Exactly one authorized submit per operation/attempt under concurrent workers; replay and ambiguous crash outcomes remain fail-closed.

**Smallest correct scope:** Protect the first paid submission boundary for one logical keyframe operation; retain its current provider and QC contracts.

**Acceptance criteria:**

- Two workers released simultaneously on the same operation cause exactly one provider submission; both return or observe one durable operation identity.
- A different request digest under the same operation ID is rejected.
- A crash between claim and provider result does not trigger a second paid submission without verified reconciliation or a new authorized attempt.

**Regression coverage:** Real SQLite two-worker concurrency test, crash-window/restart test, request-digest conflict test, and fake provider call counter. No live paid test is required for mutual exclusion.  
**Dependencies:** Before multi-worker live keyframes; independent of single-product provider acceptance.  
**Out of scope:** Replacing the workflow outbox or altering the already durable video scene-operation contract.

### FIX-006 — Protect concurrent Video Factory project updates

**Category:** Concurrency / state correctness.  
**Priority:** **P1 before parallel scene writers or multiple workers on one project**; not a blocker for sequential single-product acceptance.  
**Type:** HARDENING of an unsafe write boundary.  
**Affected flow:** VF storyboard, generated scenes, timeline, approvals and final artifact project state.  
**Blocks single-product E2E:** **NO** when writes are sequential.  
**Blocks concurrent production:** **YES** for same-project writers.

**Expected behavior:** A stale project snapshot cannot silently overwrite fields saved by another worker. Conflicts are detectable and can be retried against current state.

**Actual behavior:** `SQLiteVideoFactoryRepository.save()` replaces essentially every project column under `WHERE id=? AND owner_user_id=?`, with no expected revision or targeted-field predicate (`integrations/video_factory/repository.py:365-410`). The WF aggregate has optimistic versioning, but that does not protect the separate VF project row.

**Evidence:** Source: `integrations/video_factory/repository.py:365-410`; workflow version protection is separate (verification report §12). Tests: sequential VF persistence coverage passes; a stale-reader/same-project concurrent save assertion is absent (verification report §12/§16). Lost update is the direct consequence of the current whole-row predicate.

**Impact:** Lost scene, storyboard, approval or timeline updates can make a partially completed project inconsistent.

**Required outcome:** Conflicting project writes do not silently lose committed state; sequential behavior and owner isolation remain unchanged.

**Smallest correct scope:** Add conflict detection or safe equivalent at the VF project-save boundary and adapt its immediate callers.

**Acceptance criteria:**

- Two readers of one VF project cannot both save divergent stale full-project versions successfully without a conflict or safe merge.
- After resolving a conflict, both intended non-conflicting updates are present; owner reassignment remains rejected.
- Existing single-worker render/composition/export and restart tests stay green.

**Regression coverage:** Real SQLite concurrent/stale-reader integration test and same-project workflow/render regression; no external provider call.  
**Dependencies:** Before parallel scene work and multi-worker production; independent of FIX-005 but both gate concurrency.  
**Out of scope:** A new repository layer or database migration beyond the minimum safe write contract.

### FIX-007 — Governed correction after failed Video QC

**Category:** Recovery / operability.  
**Priority:** **P2 if automatic scene correction is required after first acceptance; P3/optional if safe operator blocking and manual replacement are sufficient.**  
**Type:** OPTIONAL FEATURE until product scope explicitly requires automatic correction; current fail-closed QC behavior is not defective.  
**Affected flow:** Failed per-scene Video QC → operator action → scene retry/composition/new QC.  
**Blocks single-product E2E:** **NO** for a happy case that passes QC; a failing case remains safely blocked.  
**Blocks concurrent production:** **NO** specifically; affects recovery throughput.

**Expected behavior if adopted:** A QC recommendation to retry one scene becomes a bounded, operator-authorized regeneration attempt with invalidated dependent composite/QC/approval, followed by fresh QC. If not adopted, the product should clearly remain blocked with a documented manual correction path.

**Actual behavior:** `qc/video_qc.py:355-436` stores `retry_scene_N` strings; `handlers.py:2177-2189` moves non-PASS Video QC to `WaitingForOperator`. The CLI can rerun QC and the operator handler has keyframe retry, but there is no configured scene-regeneration command consuming the video action (`product_video/cli.py:82-135,782-866`; `application/operator_handler.py:644-732`). The master spec requires fail-closed Video QC (`product-video-master-spec.md:517-528`), which is already met; it does not establish automatic scene regeneration as a first-run requirement.

**Evidence:** Source: the QC, handler, CLI and operator locations cited above; master spec §9.3. Tests: non-PASS gate behavior has coverage, while no workflow test exercises automatic video-scene retry (verification report §10/§16). No live failed-scene recovery run was performed.

**Impact:** A failed scene cannot be corrected through one canonical automated action; an operator must intervene outside that suggested action or abandon the run. Invalid video is not exported.

**Required outcome:** Decide whether manual blocked recovery satisfies MVP; if automatic recovery is required, execute only a specifically authorized, bounded new attempt with correct invalidation.

**Smallest correct scope:** Document/manualize current blocked recovery, or add one governed per-scene retry action if product scope selects it.

**Acceptance criteria:**

- In either scope, non-PASS Video QC never creates Final approval or export eligibility.
- If automatic correction is adopted, an authorized retry changes only the affected scene attempt, invalidates old composite/QC/Final approval, composes again and requires a new PASS report; replay does not duplicate a paid attempt.
- If manual correction is chosen, CLI/API state identifies the failed scene/reason and the documented route to a fresh render/QC, without claiming automatic retry.

**Regression coverage:** Existing QC fail-closed workflow test remains; if adopted, FAIL→authorized scene retry→new clip/composite→fresh QC integration and replay test. No paid live test for control flow.  
**Dependencies:** Product decision in §6; after a successful single-product baseline. If implemented, it relies on FIX-005/006 for concurrent paid use.  
**Out of scope:** Automatic unlimited retry loops or weakening the existing operator/QC gate.

### FIX-008 — Align MCP regression tests with the current strict contract

**Category:** Test / contract debt.  
**Priority:** **P1 for formal acceptance gate**, despite no demonstrated production-code failure in these five cases.  
**Type:** TEST DEBT; any real external MCP compatibility break discovered during caller audit would be a separate defect.  
**Affected flow:** Direct MCP render/export tests and contract expectations.  
**Blocks single-product E2E:** **YES for acceptance signoff**, **NO** as evidence of a failed provider-substituted happy path.  
**Blocks concurrent production:** **NO** specifically.

**Expected behavior:** Tests supply the current required render lineage, approved keyframe/QC evidence and exact project state; negative tests assert the relevant current fail-closed reason without depending on obsolete validation order. Direct callers either comply or receive a documented migration error.

**Actual behavior:** The combined run had **1,108 passed, 5 failed**; an isolated MCP rerun had **34 passed, 5 failed** (verification report §15). Four tests expected old export behavior/error ordering despite `RENDER_LINEAGE_REQUIRED` and exact QC/artifact checks; one expected symbolic-reference storyboard render without V2 keyframe/QC requirements (`tests/mcp_servers/test_video_factory_server.py:377-489,511-643`; `test_video_factory_paid_contract.py:295-325`; current `integrations/video_factory/server.py:2118-2149,3421-3443`). Newer Product Video export/integrity tests pass the stricter path. This supports stale-test classification, subject to the direct-caller audit.

**Evidence:** Tests: `tests/mcp_servers/test_video_factory_server.py:377-489,511-643`, `tests/mcp_servers/test_video_factory_paid_contract.py:295-325`; exact failing commands/results in verification report §15. Source: `integrations/video_factory/server.py:2118-2149,3421-3443`. The direct-caller compatibility audit remains an acceptance criterion, so a separate real compatibility defect is not ruled out.

**Impact:** Red combined gate masks new failures and leaves uncertainty about direct MCP compatibility; weakening strict source validation would reintroduce unsafe behavior.

**Required outcome:** A green combined gate that genuinely exercises the canonical render/export contract, with any real client migration identified explicitly.

**Smallest correct scope:** Update obsolete fixtures/assertions to the existing strict contract and address only any demonstrated direct-caller break.

**Acceptance criteria:**

- The same combined command completes with zero failures; positive MCP fixtures supply valid canonical lineage, approved keyframes and QC.
- Negative tests still reject missing lineage, absent/stale QC, unapproved storyboard, invalid bytes and wrong owner/project.
- Direct configured MCP callers are inventoried; no valid caller silently breaks, and any intentional contract change is documented.

**Regression coverage:** Both MCP files plus `tests/hermes_personal` combined; current export-integrity and scene-render tests retained. No paid/live provider test is required to repair stale assertions.  
**Dependencies:** Clarify current contract from source first; fix independently of feature work. Must be green before formal acceptance reporting.  
**Out of scope:** Relaxing canonical render lineage, keyframe QC or Video QC checks solely to satisfy old fixtures.

### FIX-009 — Complete practical final-export provenance

**Category:** Lineage / debuggability.  
**Priority:** **P2** for first controlled video generation; **P1 for full master-spec metadata signoff** if §10.2 is applied literally.  
**Type:** MISSING REQUIRED FEATURE for the spec’s full metadata bundle; not an MP4-integrity defect.  
**Affected flow:** PI/creative/media/QC records → immutable export metadata.  
**Blocks single-product E2E:** **NO** for producing and validating a video; **YES** for claiming full §10.2 export-provenance compliance.  
**Blocks concurrent production:** **NO**, though missing attempts complicate incident analysis.

**Expected behavior:** A final package identifies its product/variant, PI snapshot/pack and claim evidence, selected source assets, approved creative digests, prompt/model versions, keyframe hashes and QC reports, scene provider operation IDs/attempts/hashes, five approvals, technical probe, final Video QC and cumulative spend. Values link to immutable canonical records and match actual bytes.

**Actual behavior:** Export strictly verifies final SHA, decode, approval and exact PASS QC, but its `provenance` dict at `integrations/video_factory/server.py:3824-3858` omits snapshot/dossier/script/storyboard digests, keyframe QC and complete model/attempt chain; VF reference mirroring keeps hash/QC but not original URL (`product_video/mcp_adapters.py:609-620`). Master spec §10.2 explicitly lists fuller `metadata.json` fields (`product-video-master-spec.md:589-598`).

**Evidence:** Source: `integrations/video_factory/server.py:3824-3858`, `product_video/mcp_adapters.py:609-620`; master spec §10.2. Tests: current export-integrity tests verify bytes, owner/approval and QC but do not establish the complete provenance bundle (verification report §13/§16).

**Impact:** Operators must join PI, WF, VF and QC stores to explain one export; some origin data may be lost, and long-term reproduction after cleanup is harder. Final bytes remain protected.

**Required outcome:** The existing immutable package carries a versioned, practically sufficient manifest of canonical IDs/digests/settings and final media facts, without duplicating large source payloads.

**Smallest correct scope:** Extend the current export metadata from canonical retained records; preserve existing immutable export and byte verification.

**Acceptance criteria:**

- Given export metadata plus retained canonical stores, a verifier resolves one product/variant, snapshot, pack, claim evidence, selected source refs, script/scene/prompt versions, keyframe/QC, provider operation/attempt, clip/composite hashes, approvals, spend and final QC.
- Metadata references match persisted record IDs and file SHA; no entry is fabricated from caller-supplied facts.
- Repeated same-version export remains immutable/idempotent; changed bytes require a new version.

**Regression coverage:** Export-package integration with seeded canonical records; missing/stale link fail-closed or explicitly marked unavailable according to contract; existing decode/SHA/QC tests retained. A live provider run is not required to validate manifest assembly.  
**Dependencies:** FIX-003 for truthful claim evidence; otherwise independent of provider choice. Scope decision on full §10.2 signoff is recorded in §6 only if first-run acceptance criteria are being narrowed.  
**Out of scope:** New artifact database or copying full raw PI/model payloads into every export.

### FIX-010 — Image source replacement after insufficient Image QC

**Category:** Optional product improvement / recovery.  
**Priority:** **P3** unless unattended recovery from bad source sets is explicitly in the first product scope.  
**Type:** OPTIONAL FEATURE; current fail-closed image QC is correct.  
**Affected flow:** Fewer than two eligible source images → new images → fresh Image QC/Product Lock.  
**Blocks single-product E2E:** **NO** when intake has two passing images; a bad set safely blocks.  
**Blocks concurrent production:** **NO**.

**Expected behavior if adopted:** An operator or governed acquisition action supplies replacement images, and the workflow treats them as new source bytes requiring new hashes/QC before Product Lock. Automatic cleaning/reacquisition is not implied by the presence of a helper class.

**Actual behavior:** Image QC emits `reacquire_references` (`qc/image_qc.py:314`) and blocks Product Lock with non-PASS (`handlers.py:2015-2039`). `ProductImageCleaner` is referenced only by its package/tests, not the configured worker path (`preprocessing/image_cleaner.py`; verification report §5). No automatic reacquisition job is registered.

**Evidence:** Source: `qc/image_qc.py:314`, `product_video/handlers.py:2015-2039`, `preprocessing/image_cleaner.py`. Tests: fail-closed image eligibility is covered; no configured cleaning/reacquisition workflow test exists (verification report §5/§16). Automatic recovery is not a first-run spec requirement.

**Impact:** A product with poor images needs manual source replacement or remains blocked. No low-quality image is silently admitted.

**Required outcome:** Document the manual replacement process for first acceptance; implement automatic acquisition/cleaning only if required by product operations.

**Smallest correct scope:** Keep the current QC gate; add only a safe replacement route or optional acquisition action if needed.

**Acceptance criteria:**

- With <2 eligible images, Product Lock stays unavailable and the failure/reacquisition reason is visible.
- If replacement is supplied, its new bytes/identity are checked and a fresh PASS report is required; prior QC cannot authorize changed assets.
- If automation is adopted, it obeys the same containment, identity and QC gates as manual replacement.

**Regression coverage:** Existing image-QC fail-closed tests; optional workflow test with replacement assets and stale-QC invalidation. No live model test is needed for the state transition.  
**Dependencies:** Product decision in §6; independent of provider readiness and creative fixes.  
**Out of scope:** Wiring `ProductImageCleaner` solely because it exists, or allowing cleaned/reacquired assets to bypass Image QC.

### FIX-011 — Bound shared provider and browser-profile capacity

**Category:** Concurrency / operability.  
**Priority:** **P2 before expanding to concurrent automated paid production**; **P1** if multiple workers are enabled immediately.  
**Type:** HARDENING; no observed collision in the three-product offline tests.  
**Affected flow:** Multiple products/scenes/workers sharing Vertex quotas or one Flow browser profile.  
**Blocks single-product E2E:** **NO**.  
**Blocks concurrent production:** **YES** at unbounded/unknown capacity.

**Expected behavior:** The runtime admits no more paid provider jobs than configured capacity and grants exclusive ownership of a browser profile when Flow is used; waiting work remains durable and resumes without path or operation collision.

**Actual behavior:** Coordinator caps a batch at three and outbox workers lease jobs (`automation/coordinator.py:213-266`; `workflows/worker.py:75-137`), but there is no demonstrated shared provider quota/profile lease. Flow state is process-local (`google_flow_provider.py:47-53`). VF same-project writes also lack conflict protection (FIX-006). Ten-product/live provider load was not tested.

**Evidence:** Source: `automation/coordinator.py:213-266`, `workflows/worker.py:75-137`, `integrations/video_factory/google_flow_provider.py:47-53`. Tests: offline three-product behavior passes, but no ten-product/live quota/profile contention run was performed (verification report §12/§15/§16). This records an unvalidated scaled boundary, not an observed three-product collision.

**Impact:** Rate-limit spikes, profile contention or duplicate/ambiguous work during scaled automation. This is a capacity risk, not proof of a current three-product data collision.

**Required outcome:** Explicit provider/browser capacity and exclusive profile ownership for enabled browser providers before raising automation concurrency.

**Smallest correct scope:** Bound admission at the existing provider/job entry points and protect a browser profile only where Flow is enabled.

**Acceptance criteria:**

- Two workers cannot operate the same browser profile simultaneously; excess jobs wait durably and later resume.
- Provider in-flight count never exceeds the configured limit across workers; rate-limit/timeout leaves a recoverable state.
- Ten-product fake-provider stress has isolated workflow/project/media paths and no duplicate paid-operation IDs.

**Regression coverage:** Multi-worker SQLite/in-process capacity test, browser-profile lock/restart test if Flow enabled, and offline three-/ten-product load smoke; one controlled provider-quota acceptance when scaling live.  
**Dependencies:** FIX-005/006 before concurrent paid work; FIX-001 if Flow enabled.  
**Out of scope:** Raising the current daily product cap as part of this fix or introducing a new queue/broker.

### Findings intentionally excluded from the required fix list

- **Legacy daily importer/source-root route and forwarding modules:** Present and reachable, but no broken import, stale registration or production failure was demonstrated. The `src/hermes/mcp/video_factory/server.py` shim is still the configured runbook entry point (`docs/hermes-personal/product-video-runbook.md:225-228`). Inventory before any later removal; no fix ticket or file move is justified now.
- **ProductImageCleaner not wired:** Included only in conditional FIX-010 because clean-source QC already rejects contamination and no current acceptance rule requires automatic inpainting.
- **Live acceptance evidence absent:** A release/verification gate, not a code defect. A live run must use the actually selected PI/model/QC/keyframe/video providers and inspect output. It cannot be replaced by fake-provider tests.
- **No selected provider on this review host:** Setup state observed with read-only config resolution; not evidence that every deployment is unconfigured. Selecting a provider belongs to the controlled-run checklist, not a production-code fix.

## 3. Fix Priority Groups

These groups place each **FIX** once at the earliest stage actually required. Conditional scope is noted in the issue, not duplicated across groups.

### MUST FIX BEFORE CONTROLLED REAL E2E

1. **FIX-001** — truthful provider readiness; implement real Flow only if selected, otherwise disable Flow and select/live-verify Vertex.
2. **FIX-002** — VF storyboard persistence failure must block keyframe/gate advancement.
3. **FIX-003** — claim-specific PI evidence and vendor-neutral official sources.
4. **FIX-004** — end-frame handoff or an explicit early unsupported-policy gate; unconstrained configured V2 output can request it.
5. **FIX-008** — green combined MCP/Product Video validation gate without weakening strict render/export checks.

### MUST FIX BEFORE CONCURRENT / AUTOMATED PRODUCTION

1. **FIX-005** — one first paid keyframe submit per logical operation across workers.
2. **FIX-006** — no silent lost VF project updates under concurrent writers.
3. **FIX-011** — bounded shared provider capacity and Flow profile exclusivity if enabled.

### SHOULD FIX AFTER INITIAL E2E ACCEPTANCE

1. **FIX-009** — practical export provenance enrichment. If formal first-run signoff requires every §10.2 field, promote this to the first group; the byte-validity check itself already works.
2. **FIX-007** — governed Video QC scene regeneration **only if** product operations require it; otherwise retain safe operator blocking with a documented manual correction route.

### CAN WAIT / OPTIONAL

1. **FIX-010** — automatic image reacquisition/cleaning. Manual replacement with fresh Image QC is sufficient for a controlled product with two eligible references.

## 4. Dependency Order

This is a set of prerequisites, **not** an implementation sequence or schedule:

```text
Provider choice ─→ FIX-001 truthful readiness ─→ live provider acceptance
FIX-003 truthful PI evidence ─→ meaningful creative-quality assessment
FIX-002 VF storyboard consistency ─→ trustworthy keyframe/storyboard/render acceptance
FIX-004 end-frame contract ─→ acceptance of scenes requesting end frames
FIX-008 green contract tests ─→ formal acceptance claim
FIX-003 ─→ FIX-009 truthful claim/evidence lineage
FIX-005 + FIX-006 ─→ concurrent paid scene/keyframe work
FIX-001 (if Flow enabled) + FIX-005 + FIX-006 ─→ FIX-011 scaled browser/provider operation
Initial single-product PASS ─→ optional FIX-007 / FIX-010 recovery automation
```

Independent work can proceed without coupling: stale MCP fixtures (FIX-008), VF storyboard fail-closed handling (FIX-002), and PI evidence mapping (FIX-003) do not depend on one another. Keyframe atomicity and VF conflict safety are separate concurrency boundaries. Full Flow browser implementation depends on a product/provider choice; the truthful readiness requirement does not.

## 5. Existing Behavior To Preserve

- Exactly five operator gates, owner/workflow/project/artifact/version-bound approvals, and rejection/invalidation.
- Atomic product claim and workflow-created/ledger-marked crash recovery.
- Workflow aggregate versioning, event/outbox transaction, worker leases/heartbeats/quarantine and restart recovery.
- V2 creative contracts, versioned prompt/response validation and one bounded repair attempt.
- Image decode/hash/dedup/identity/risk/score checks and at least two eligible references before Product Lock.
- Scene-level reference selection and reference SHA verification before keyframe generation.
- Keyframe QC before Storyboard approval and operator-authorized keyframe regeneration.
- Provider-neutral scene request, durable video scene operation IDs, provider pinning and no silent post-submit fallback.
- Ordered clip/composite technical validation and approval invalidation after changed media.
- Exact Final approval, PASS Video QC, full decode, SHA and immutable versioned export checks.
- Offline fake-provider E2E coverage; never represent it as live provider acceptance.

## 6. Open Decisions

Only these scope choices affect the next technical specification:

1. **First live render provider:** Is Google Flow required for the first acceptance, or is Vertex-only acceptable while Flow is explicitly unavailable? The example config names Flow, but this review host has no selected provider. This determines whether FIX-001 requires a full browser implementation now or only truthful unavailability plus Vertex acceptance.
2. **End-frame provider policy:** For a provider without first/last-frame conditioning, may a scene carry an end frame for storyboard/QC only, or must `generated/required` be rejected before paid generation unless the provider can consume it? Scene identity/count must be fixed either way (FIX-004).
3. **Failed Video QC recovery scope:** Does MVP require an operator-authorized scene-regeneration action, or is safe blocked state with manual correction acceptable after the first live happy case (FIX-007)? Current spec establishes blocking, not automatic retry.
4. **Bad-source recovery scope:** Is manual replacement of a failed image set acceptable, or is automatic reacquisition required (FIX-010)? The Image QC eligibility rule itself is settled.
5. **First acceptance metadata:** Must the first controlled live export contain every field listed in master spec §10.2, or is the existing truthful byte/QC metadata plus retained canonical stores sufficient for initial diagnostic acceptance, with FIX-009 before formal MVP signoff? Do not silently declare the spec complete while fields are absent.

No decision is needed to keep the existing five gates, strict QC/export checks, or to avoid duplicate paid submissions; those requirements are clear.

## 7. Spec Inputs

Carry these **behavioral** requirements into the next technical fix specification:

1. Enabled providers truthfully report readiness; a submitted job corresponds to real externally recoverable work, with stable provider identity across restart. Unsupported/unavailable providers fail before paid submission.
2. Workflow advancement after Scene Plan approval requires a successful, matching VF storyboard persistence result; failed writes cannot launch keyframes or create a Storyboard gate.
3. Creative claims retain exact PI snapshot/pack claim-to-evidence/source relationships for the locked product and variant. Unknown, unsupported or cross-product evidence never becomes supported.
4. Start/end frames share one scene ID and differ by frame role. Package validation counts scenes correctly, checks both frame digests/QC, and honors or rejects end-frame provider requirements before paid work.
5. Exactly one worker owns the first paid keyframe submission for a logical operation/attempt; crash and replay never blindly duplicate it.
6. Concurrent VF project changes cannot silently overwrite committed fields; a stale writer observes a conflict or safe equivalent.
7. Video QC non-PASS remains an absolute Final-approval/export block. If scene correction is in scope, it requires bounded authorization, new attempt identity, downstream invalidation and fresh QC.
8. Direct MCP render/export tests and callers use the canonical strict lineage, approval and QC contract. The combined regression gate is green without weakening production validation.
9. Final export retains truthful technical facts and immutable bytes. Its required provenance scope is explicit and contains canonical IDs/digests for the approved inputs, media operations, QC and spend.
10. If image reacquisition or multi-worker operation is enabled, all new source bytes pass fresh Image QC; provider/browser capacity is bounded and durable across workers.
11. One controlled real product traverses all five approvals using its selected live PI/model/QC/keyframe/video providers and produces an inspected export. Offline tests are necessary but not a substitute for that acceptance evidence.
