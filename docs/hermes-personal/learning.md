# Hermes Personal Governed Learning, Memory, and Knowledge

## Overview

The Hermes Personal Learning system enables Hermes to continuously improve across executions through owner-scoped memory, evidence-backed knowledge, approved procedural skills, relevant retrieval, measured effectiveness, and safe rollback.

The system adheres strictly to the narrow-waist architecture:
- **No model-weight training or fine-tuning**: Improvement is achieved through governed memory, structured knowledge retrieval, and versioned skill projections.
- **Evidence-backed governance**: Unbacked assertions, failed task outcomes, and rejected candidates are strictly excluded from positive learning.
- **Owner isolation**: All memory, knowledge, and procedural skills are strictly partitioned by `owner_user_id`. Cross-owner leakage is prevented at the schema and query levels.
- **Gate 4 Human-In-The-Loop approval**: Low-risk explicit preferences may auto-promote, but knowledge and procedural candidates always require evaluation, versioning, and owner approval.

---

## Architecture & Data Flow

```
┌────────────────────────────────────────────────────────┐
│ Execution Trace / Task Outcome / Owner Feedback       │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Learning Candidate + Evidence Extraction               │
│ - Digest uniqueness (owner, kind, digest)             │
│ - Immutable task outcome validation                   │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ CandidateEvaluator & Policy Checks                     │
│ - Sensitive data & secrets rejection                  │
│ - Polarity & source outcome validation                │
│ - Low-risk preference -> eligible_auto                │
│ - Knowledge / Procedure -> needs_approval              │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ PromotionService & Gate 4 Approval Integration        │
│ - Auto-promote explicit low-risk preferences          │
│ - Submit HITL approval request for knowledge/procedure│
│ - Atomic version activation & predecessor supersession │
│ - Deterministic version rollback                       │
└────────────┬─────────────────────────────┬─────────────┘
             │                             │
             ▼                             ▼
┌────────────────────────────┐┌───────────────────────────┐
│ ApprovedLearningRetriever  ││ ProceduralSkillPublisher  │
│ & AgentContextAssembler    ││ - Versioned SKILL.md      │
│ - Strict owner isolation   ││ - Allowed capabilities    │
│ - Bounded turn context     ││ - Atomic projection update│
│ - HermesTurnService inject ││ - Safe rollback           │
└────────────────────────────┘└───────────────────────────┘
```

---

## Core Components

### 1. Persistence Models & Repository (`hermes_personal/learning/models.py`, `repository.py`)
- **`LearningCandidate`**: Immutable candidate records with kind (`preference`, `knowledge`, `procedure`), title, content, content digest, and status (`draft`, `evaluated`, `pending_approval`, `approved`, `rejected`).
- **`EvidenceRef`**: Digest-addressed evidence references citing turn traces, workflows, artifacts, or feedback.
- **`TaskOutcome`**: Immutable execution outcomes (`success`, `failure`, `cancelled`).
- **`CandidateEvaluation`**: Evaluation record capturing evaluator name, decision (`eligible_auto`, `needs_approval`, `reject`), score, reason, and evidence summary.
- **`LearningVersion`**: Append-only numbered versions (`1`, `2`, ...) with status (`active`, `revoked`, `superseded`).
- **`LearningEvent`**: Audit trail of candidate creation, status transitions, versioning, and rollback events.

### 2. Candidate Evaluation Policy (`hermes_personal/learning/evaluator.py`)
- Validates evidence presence and digest integrity.
- Enforces outcome polarity: failed task outcomes cannot produce positive learning candidates.
- Detects and rejects secrets, API keys, private keys, and passwords.
- Enforces promotion eligibility:
  - `kind="preference"` + low risk + explicit feedback + score >= 0.8 -> `eligible_auto`.
  - `kind in ("knowledge", "procedure")` -> `needs_approval` (never auto-promoted).
  - Invalid, unbacked, or sensitive candidates -> `reject`.

### 3. Promotion & Rollback Service (`hermes_personal/learning/promotion.py`)
- Integrates with Gate 4 `ApprovalService` for multi-channel human-in-the-loop review.
- Auto-promotes low-risk preferences immediately upon evaluation.
- Promotes approved candidates into numbered active versions and supersedes prior active versions.
- Supports deterministic rollback: revokes target version and reactivates immediate non-revoked predecessor.

### 4. Approved Retrieval & Context Assembly (`hermes_personal/learning/retrieval.py`, `context.py`)
- **`ApprovedLearningRetriever`**: Queries only active approved versions for the authenticated owner. Excludes draft, rejected, superseded, and revoked items.
- Token overlap and workflow tag relevance scoring with deterministic `version_id` tie-breaking.
- **`AgentContextAssembler`**: Compiles bounded owner preferences, approved knowledge, active procedures, and capability summaries into structured `AgentContext`.
- **`HermesTurnService`**: Automatically injects assembled personal context into the agent turn execution pipeline.

### 5. Preference Memory Governance (`hermes_personal/learning/memory_policy.py`)
- Risk matrix categorizing preferences into formatting, tone, locale, UI defaults, identity, financial, destructive, legal/medical, or credential.
- Low-risk categories with explicit user confirmation are auto-promotable.
- Generates markdown projections for upstream `USER.md` profile integration.

### 6. Safe Procedural Skill Publication (`hermes_personal/learning/skill_publisher.py`)
- Generates valid upstream `SKILL.md` files with YAML frontmatter containing `name`, `description`, `version`, `owner`, `digest`, and `allowed-capabilities`.
- Enforces capability bounds (Gate 3 capability catalog) and rejects unsafe execution directives (`rm -rf`, `curl | bash`, `eval`).
- Atomic projection updates and clean rollback handling.

### 7. Effectiveness Metrics (`hermes_personal/learning/metrics.py`)
- Tracks success rate, correction rate, approval rate, p50/p95 latency, and minor-unit costs by learning version.
- Reports `insufficient_data` when sample count is below threshold, preventing premature claims of improvement.

---

## Verification & Testing

Run all learning and integration suites:
```bash
# Run learning suite
uv run pytest tests/hermes_personal/learning -q

# Run broad gateway, capability, and learning suites
uv run pytest tests/hermes_personal/learning tests/hermes_personal/gateway tests/hermes_personal/capabilities -q

# Run static analysis
uv run ruff check hermes_personal/learning tests/hermes_personal/learning hermes_personal/storage/sqlite.py
```
