# Hermes Governed Learning Memory And Knowledge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Hermes improve across executions through owner-scoped memory, evidence-backed knowledge, approved procedural skills, relevant retrieval, measured effectiveness, and rollback.

**Architecture:** Execution traces and explicit feedback produce immutable learning candidates. Policy permits automatic promotion only for low-risk preferences; knowledge and procedural candidates require evaluation and owner approval before a version enters the retrieval index or skill projection. A context assembler injects only approved, relevant, non-revoked material into the canonical Agent Turn.

**Tech Stack:** Python 3.10+, SQLite FTS5 with deterministic fallback, upstream memory/skill utilities, Gate 4 approvals, dataclasses, pytest, `uv`.

## Global Constraints

- Gates 1-5 must pass before this gate starts.
- This gate does not fine-tune or claim to train model weights.
- Failed workflows and unapproved artifacts are excluded from positive learning.
- Low-risk preferences may auto-promote; knowledge and procedural skills require evidence, evaluation, versioning, and owner approval.
- Every promoted knowledge/skill version supports rollback and remains auditable.
- Knowledge storage is canonical; Markdown and upstream skill files are generated projections.
- Retrieval is owner-scoped and relevance-limited; cross-owner leakage is a release blocker.
- Tests use local fixtures/fakes and no remote embedding or paid provider.

---

## File Map

- `hermes_personal/learning/models.py`: candidates, evidence, evaluations, versions, and outcomes.
- `hermes_personal/learning/repository.py`: immutable candidate/version/event persistence.
- `hermes_personal/learning/evaluator.py`: evidence and outcome quality evaluation.
- `hermes_personal/learning/promotion.py`: approval-gated promotion and rollback.
- `hermes_personal/learning/retrieval.py`: owner-scoped approved retrieval.
- `hermes_personal/learning/context.py`: Agent Turn context assembly.
- `hermes_personal/learning/memory_policy.py`: low-risk preference classification.
- `hermes_personal/learning/skill_publisher.py`: safe upstream skill projection.
- `hermes_personal/learning/metrics.py`: effectiveness and regression measures.

### Task 1: Persist Learning Candidates, Evidence, Versions, And Outcomes

**Files:**
- Create: `hermes_personal/learning/models.py`
- Create: `hermes_personal/learning/repository.py`
- Create: `hermes_personal/learning/__init__.py`
- Modify: `hermes_personal/storage/sqlite.py`
- Test: `tests/hermes_personal/learning/test_repository.py`

**Interfaces:**
- Consumes: owner, source workflow/turn/tool trace, feedback, artifact refs, and terminal outcome.
- Produces: immutable `LearningCandidate`, `LearningVersion`, and `TaskOutcome` records.

- [ ] **Step 1: Write immutable persistence tests**

```python
def test_candidate_requires_owner_source_and_evidence(repository, candidate_factory):
    with pytest.raises(InvalidCandidate, match="evidence"):
        repository.create_candidate(candidate_factory(evidence=()))

def test_failed_workflow_cannot_be_positive_evidence(repository, candidate_factory):
    with pytest.raises(InvalidCandidate, match="successful outcome"):
        repository.create_candidate(candidate_factory(source_outcome="failed", polarity="positive"))

def test_versions_are_append_only(repository, approved_candidate):
    first = repository.create_version(approved_candidate.candidate_id, content="v1")
    second = repository.create_version(approved_candidate.candidate_id, content="v2")
    assert (first.version, second.version) == (1, 2)
    assert repository.get_version(first.version_id).content == "v1"
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/hermes_personal/learning/test_repository.py -q`

Expected: FAIL on missing learning package.

- [ ] **Step 3: Implement exact records and schema**

```python
LearningKind = Literal["preference", "knowledge", "procedure"]
CandidateStatus = Literal["draft", "evaluated", "pending_approval", "approved", "rejected"]
VersionStatus = Literal["active", "revoked", "superseded"]

@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source_type: Literal["turn", "workflow", "artifact", "feedback", "tool_trace"]
    source_id: str
    digest: str
    excerpt: str

@dataclass(frozen=True)
class LearningCandidate:
    candidate_id: str
    owner_user_id: str
    kind: LearningKind
    title: str
    content: str
    evidence: tuple[EvidenceRef, ...]
    source_outcome_id: str | None
    status: CandidateStatus
    created_at: datetime
```

Add normalized tables for candidates, evidence, evaluations, versions, task outcomes, and learning events. Store content digest and uniqueness `(owner_user_id, kind, digest)` to make repeated extraction idempotent. No trigger may auto-mark knowledge/procedure approved.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/hermes_personal/learning/test_repository.py -q`

Expected: all persistence tests pass.

```powershell
git add -- hermes_personal/storage/sqlite.py hermes_personal/learning tests/hermes_personal/learning/test_repository.py
git commit -m "feat: persist governed learning records"
```

### Task 2: Evaluate Evidence And Execution Outcomes

**Files:**
- Create: `hermes_personal/learning/evaluator.py`
- Test: `tests/hermes_personal/learning/test_evaluator.py`

**Interfaces:**
- Consumes: candidate, source outcome, corrections, approval result, latency, and cost.
- Produces: deterministic `CandidateEvaluation` with decision and reason codes.

- [ ] **Step 1: Write evaluator policy tests**

Test evidence digest validity, minimum one independent evidence item for knowledge, successful source outcome for positive procedure, explicit feedback precedence, contradiction detection, sensitive-data rejection, low-confidence pending state, and duplicate-content detection.

- [ ] **Step 2: Verify red and implement deterministic policy**

Run: `uv run pytest tests/hermes_personal/learning/test_evaluator.py -q`

Expected: FAIL on missing evaluator.

Define `CandidateEvaluation(evaluation_id, candidate_id, evidence_score, outcome_score, risk, decision, reason_codes, created_at)`. `decision` is one of `eligible_auto`, `needs_approval`, or `reject`. Only `kind=preference`, low risk, explicit owner feedback, no sensitive content, and score at/above configured threshold may be `eligible_auto`; knowledge/procedure always become `needs_approval` when valid.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/learning/test_evaluator.py -q`

Expected: all policy tests pass.

```powershell
git add -- hermes_personal/learning/evaluator.py tests/hermes_personal/learning/test_evaluator.py
git commit -m "feat: evaluate learning candidates"
```

### Task 3: Promote With Approval, Versioning, And Rollback

**Files:**
- Create: `hermes_personal/learning/promotion.py`
- Test: `tests/hermes_personal/learning/test_promotion.py`

**Interfaces:**
- Consumes: evaluation, Gate 4 approval service, expected candidate version, authenticated owner.
- Produces: active `LearningVersion`, supersession, rejection, and rollback events.

- [ ] **Step 1: Write promotion lifecycle tests**

```python
def test_knowledge_requires_owner_approval(promotion_service, evaluated_knowledge):
    pending = promotion_service.request_promotion(evaluated_knowledge)
    assert pending.approval_id is not None
    assert promotion_service.active_versions(evaluated_knowledge.owner_user_id) == ()

def test_rollback_reactivates_prior_version_and_removes_new_index_entry(promotion_service, approved_versions):
    v1, v2 = approved_versions
    result = promotion_service.rollback(v2.version_id, owner_user_id=v2.owner_user_id, expected_version=v2.version)
    assert result.active_version_id == v1.version_id
    assert result.revoked_version_id == v2.version_id
```

- [ ] **Step 2: Verify red and implement transactional promotion**

Run: `uv run pytest tests/hermes_personal/learning/test_promotion.py -q`

Expected: FAIL on missing service.

Promotion must verify owner, evaluation ID, candidate digest/version, and approval digest/version. In one transaction, supersede the previous active version, activate the new version, append a learning event, and enqueue index/skill projection work. Rollback revokes the selected version and activates the immediate approved predecessor; it never deletes either version.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/learning/test_promotion.py -q`

Expected: all lifecycle tests pass.

```powershell
git add -- hermes_personal/learning/promotion.py tests/hermes_personal/learning/test_promotion.py
git commit -m "feat: promote and rollback approved learning"
```

### Task 4: Retrieve Approved Knowledge Into Relevant Agent Turns

**Files:**
- Create: `hermes_personal/learning/retrieval.py`
- Create: `hermes_personal/learning/context.py`
- Modify: `hermes_personal/orchestration/turn_service.py`
- Test: `tests/hermes_personal/learning/test_retrieval.py`
- Test: `tests/hermes_personal/learning/test_context_integration.py`

**Interfaces:**
- Consumes: owner, query/turn content, workflow type, active approved versions, transcript summary.
- Produces: ranked `RetrievedLearning` records and bounded `AgentContext`.

- [ ] **Step 1: Write isolation, relevance, and exclusion tests**

Test owner isolation, approved-only filtering, revoked/superseded exclusion, relevance ordering, deterministic tie-break, max item/token budget, failed-outcome exclusion, and no result for unrelated query.

- [ ] **Step 2: Verify red and implement local retrieval**

Run: `uv run pytest tests/hermes_personal/learning/test_retrieval.py -q`

Expected: FAIL on missing retrieval.

Index active versions by owner/kind/title/content/tags with SQLite FTS5. Provide a deterministic normalized-token fallback when FTS5 is unavailable. Rank by relevance, explicit workflow tag, confidence, and recency; stable tie-break is version ID. Return source IDs/digests for audit.

- [ ] **Step 3: Assemble context before invoking upstream AIAgent**

`AgentContextAssembler.assemble(request, history)` must combine bounded session history, owner preferences, approved knowledge/procedures, active workflow summary, and compact capability summaries. Update `HermesTurnService` to call it before `UpstreamAgentPort.run`; raw unapproved candidates and full histories from other channels are forbidden.

- [ ] **Step 4: Verify and commit**

```powershell
uv run pytest tests/hermes_personal/learning/test_retrieval.py tests/hermes_personal/learning/test_context_integration.py tests/hermes_personal/gateway/test_turn_service.py -q
git add -- hermes_personal/learning/retrieval.py hermes_personal/learning/context.py hermes_personal/orchestration/turn_service.py tests/hermes_personal/learning
git commit -m "feat: retrieve approved learning into agent turns"
```

Expected: all tests pass; the spy agent receives relevant approved knowledge and never another owner's content.

### Task 5: Govern Automatic Preference Memory

**Files:**
- Create: `hermes_personal/learning/memory_policy.py`
- Test: `tests/hermes_personal/learning/test_memory_policy.py`

**Interfaces:**
- Consumes: explicit owner statement plus candidate evaluation.
- Produces: auto-promotion decision or approval-required reason.

- [ ] **Step 1: Write a risk matrix**

Allow explicit locale, response brevity, preferred channel formatting, and reversible UI defaults. Require approval for identity, credentials, payment/budget, publishing, legal/medical facts, provider authorization, destructive defaults, inferred personal attributes, and third-party information. Reject secrets from storage.

- [ ] **Step 2: Verify red and implement exact classifier rules**

Run: `uv run pytest tests/hermes_personal/learning/test_memory_policy.py -q`

Expected: FAIL on missing policy.

Rules are deterministic category/risk checks over typed candidate metadata; do not ask an LLM to authorize its own memory write. Accepted preferences are versioned through `PromotionService` and projected to upstream `USER.md` only after database commit.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/learning/test_memory_policy.py -q`

Expected: all allow/deny cases pass.

```powershell
git add -- hermes_personal/learning/memory_policy.py tests/hermes_personal/learning/test_memory_policy.py
git commit -m "feat: govern owner preference memory"
```

### Task 6: Publish Approved Procedural Skills Safely

**Files:**
- Create: `hermes_personal/learning/skill_publisher.py`
- Test: `tests/hermes_personal/learning/test_skill_publisher.py`

**Interfaces:**
- Consumes: active approved procedure version and Gate 3 allowed capabilities/workflows.
- Produces: versioned upstream-loadable skill projection and rollback-safe activation pointer.

- [ ] **Step 1: Write publisher safety tests**

Test approved-only publication, owner/scope validation, frontmatter generation, allowed capability subset, prohibited shell/network/provider logic rejection, atomic file replacement, unchanged digest no-op, and rollback restoring the prior projection.

- [ ] **Step 2: Verify red and implement projection**

Run: `uv run pytest tests/hermes_personal/learning/test_skill_publisher.py -q`

Expected: FAIL on missing publisher.

Write generated versions under `skills/hermes-personal/generated/<skill-id>/versions/<version>/SKILL.md`; update an activation manifest atomically after upstream skill loader validation succeeds. The database version is truth. Generated Markdown includes candidate/version/evidence digests and exact allowed stable IDs, never MCP wire names.

- [ ] **Step 3: Verify with upstream skill loader and commit**

```powershell
uv run pytest tests/hermes_personal/learning/test_skill_publisher.py tests/hermes_personal/capabilities/test_domain_skills.py -q
git add -- hermes_personal/learning/skill_publisher.py tests/hermes_personal/learning/test_skill_publisher.py
git commit -m "feat: publish approved procedural skills"
```

Expected: all projections load and policy checks pass.

### Task 7: Measure Learning Effectiveness End To End

**Files:**
- Create: `hermes_personal/learning/metrics.py`
- Create: `tests/hermes_personal/learning/test_learning_e2e.py`
- Create: `docs/hermes-personal/learning.md`

**Interfaces:**
- Consumes: task outcome, corrections, approvals, latency, cost, and retrieved version IDs.
- Produces: per-version effectiveness aggregates and Gate 6 acceptance evidence.

- [ ] **Step 1: Add metric aggregation tests**

Measure success rate, correction rate, approval rate, p50/p95 latency, and cost minor units by skill/knowledge version. A zero-sample window reports `insufficient_data`; it never reports improvement. Compare only equivalent workflow types and provider policies.

- [ ] **Step 2: Add the later-turn acceptance scenario**

Complete a successful product research workflow, create an evidence-backed knowledge candidate, approve it from another owner channel, begin a later relevant turn, and assert the exact approved version is retrieved. Roll it back and assert the following turn no longer receives it. Add negative cases for failed workflow, rejected candidate, unrelated query, and another owner.

- [ ] **Step 3: Run Gate 6 verification**

```powershell
uv run pytest tests/hermes_personal/learning tests/hermes_personal/gateway tests/hermes_personal/capabilities -q
git diff --check
```

Expected: all suites pass and diff check is empty.

- [ ] **Step 4: Commit**

```powershell
git add -- hermes_personal/learning/metrics.py tests/hermes_personal/learning/test_learning_e2e.py docs/hermes-personal/learning.md
git commit -m "test: prove governed hermes learning"
```

## Gate 6 Exit Criteria

- Only low-risk explicit preferences can auto-promote.
- Knowledge/procedures require evidence, evaluation, versioning, and owner approval.
- Failed workflows, rejected candidates, stale approvals, and revoked versions cannot influence positive retrieval.
- Relevant approved knowledge reaches later Agent Turns with strict owner isolation.
- Procedural skill projections validate through upstream loaders and can roll back.
- Effectiveness is measured from outcomes/corrections/approvals/latency/cost without claiming model-weight training.
