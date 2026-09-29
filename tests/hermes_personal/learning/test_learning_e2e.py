from __future__ import annotations

import asyncio
from typing import Any, Mapping
import pytest

from hermes_personal.contracts import (
    AgentTurnRequest,
    PrincipalContext,
)
from hermes_personal.identity import IdentityRepository
from hermes_personal.learning.context import AgentContextAssembler
from hermes_personal.learning.evaluator import CandidateEvaluator
from hermes_personal.learning.memory_policy import PreferenceMemoryPolicy
from hermes_personal.learning.metrics import (
    LearningExecutionMetric,
    LearningMetricsEngine,
)
from hermes_personal.learning.models import (
    EvidenceRef,
    LearningCandidate,
    TaskOutcome,
)
from hermes_personal.learning.promotion import PromotionService
from hermes_personal.learning.repository import LearningRepository
from hermes_personal.learning.retrieval import ApprovedLearningRetriever
from hermes_personal.learning.skill_publisher import ProceduralSkillPublisher
from hermes_personal.orchestration.event_repository import EventRepository
from hermes_personal.orchestration.ports import AgentOutput
from hermes_personal.orchestration.turn_service import HermesTurnService
from hermes_personal.sessions import SessionRepository
from hermes_personal.storage.sqlite import connect as sqlite_connect
from hermes_personal.workflows.approvals import ApprovalService


class RecordingAgent:
    def __init__(self):
        self.received_histories: list[tuple[Mapping[str, Any], ...]] = []

    def run(self, request: AgentTurnRequest, history: tuple[Mapping[str, Any], ...]):
        self.received_histories.append(history)
        yield AgentOutput("text_delta", {"text": f"Executed turn for {request.message}"})
        yield AgentOutput("completed", {"status": "success"})


class FakeTranscript:
    def __init__(self):
        self.events = []
        self.user_turns = []

    @property
    def history(self) -> tuple[Mapping[str, Any], ...]:
        return tuple({"role": "user", "content": t} for t in self.user_turns)

    def append_user_turn(self, text: str) -> None:
        self.user_turns.append(text)

    def append_event(self, event: Any) -> None:
        self.events.append(event)


class FakeTranscriptFactory:
    def __init__(self):
        self.transcript = FakeTranscript()

    def for_session(self, session_id: str) -> FakeTranscript:
        return self.transcript


@pytest.fixture
def db_conn(tmp_path):
    conn = sqlite_connect(tmp_path / "e2e_test.db")
    conn.execute("INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) VALUES ('owner_alice', 'Alice', '2026-08-24T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) VALUES ('owner_bob', 'Bob', '2026-08-24T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO channel_identity (channel, external_subject, owner_user_id, created_at) VALUES ('cli', 'alice_cli', 'owner_alice', '2026-08-24T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO channel_identity (channel, external_subject, owner_user_id, created_at) VALUES ('cli', 'bob_cli', 'owner_bob', '2026-08-24T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO conversation_session (session_id, owner_user_id, channel, external_conversation_id, created_at, updated_at) VALUES ('sess_alice', 'owner_alice', 'cli', 'ext_alice', '2026-08-24T00:00:00Z', '2026-08-24T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO conversation_session (session_id, owner_user_id, channel, external_conversation_id, created_at, updated_at) VALUES ('sess_bob', 'owner_bob', 'cli', 'ext_bob', '2026-08-24T00:00:00Z', '2026-08-24T00:00:00Z')")
    conn.commit()
    yield conn
    conn.close()


def test_full_governed_learning_lifecycle_e2e(db_conn, tmp_path):
    """E2E test proving knowledge extraction, evaluation, approval, turn injection, rollback, isolation, skill projection, and metrics."""
    repository = LearningRepository(db_conn)
    approval_service = ApprovalService(db_conn)
    evaluator = CandidateEvaluator()
    promotion_service = PromotionService(repository, approval_service)
    retriever = ApprovedLearningRetriever(repository)
    assembler = AgentContextAssembler(retriever)
    memory_policy = PreferenceMemoryPolicy()
    skill_publisher = ProceduralSkillPublisher(tmp_path / "skills")
    metrics_engine = LearningMetricsEngine()

    # 1. Product Research workflow records successful outcome
    outcome = TaskOutcome(
        outcome_id="outcome_pr_1",
        source_type="workflow",
        source_id="wf_pr_100",
        status="success",
        details="Product research completed with 5 competitors analyzed",
    )
    repository.record_task_outcome(outcome)

    # 2. Extract knowledge candidate backed by valid evidence
    evidence = EvidenceRef(
        evidence_id="ev_pr_1",
        source_type="workflow",
        source_id="wf_pr_100",
        digest="sha256:abc11223344",
        excerpt="Competitor analysis shows 15-second product demo has highest conversion.",
        polarity="positive",
    )
    candidate = LearningCandidate(
        candidate_id="cand_pr_know_1",
        owner_user_id="owner_alice",
        kind="knowledge",
        title="High-Converting Video Duration",
        content="Keep product demo videos to 15 seconds for optimal TikTok conversion.",
        evidence=(evidence,),
        source_outcome_id="outcome_pr_1",
    )
    created_cand = repository.create_candidate(candidate)
    assert created_cand.status == "draft"

    # 3. Candidate evaluation: Knowledge MUST require approval (never auto-promote)
    evaluation = evaluator.evaluate(created_cand, source_outcome=outcome)
    assert evaluation.decision == "needs_approval"
    assert evaluation.score >= 0.7

    # 4. Request promotion -> submits to Gate 4 approval workflow
    req_result = promotion_service.request_promotion(created_cand, evaluation)
    assert req_result.status == "pending_approval"
    assert req_result.approval_id is not None

    # Before approval, retrieval returns nothing
    retrieved_before = retriever.retrieve(owner_user_id="owner_alice", query="TikTok conversion demo")
    assert len(retrieved_before) == 0

    # 5. Owner approves promotion -> creates active version v1
    approval_service.approve(req_result.approval_id)
    v1 = promotion_service.approve_promotion(
        approval_id=req_result.approval_id,
        owner_user_id="owner_alice",
        candidate_id="cand_pr_know_1",
        expected_version=1,
    )
    assert v1.version == 1
    assert v1.status == "active"

    # 6. Later relevant Agent Turn receives the approved knowledge in context
    identity_repo = IdentityRepository(db_conn)
    session_repo = SessionRepository(db_conn)
    event_repo = EventRepository(db_conn)
    transcript_factory = FakeTranscriptFactory()
    recording_agent = RecordingAgent()

    turn_service = HermesTurnService(
        identity_repository=identity_repo,
        session_repository=session_repo,
        event_repository=event_repo,
        transcript_factory=transcript_factory,
        agent=recording_agent,
        context_assembler=assembler,
    )

    request_alice = AgentTurnRequest(
        principal=PrincipalContext(actor_id="alice_cli", owner_user_id="owner_alice", channel="cli", session_id="sess_alice"),
        turn_id="turn_alice_1",
        message="Create a TikTok video outline for our product demo",
    )

    async def _run_turn(req):
        res = []
        async for ev in turn_service.handle(req):
            res.append(ev)
        return res

    events = asyncio.run(_run_turn(request_alice))
    assert any(e.event_type == "completed" for e in events)

    # Verify agent received approved knowledge
    assert len(recording_agent.received_histories) == 1
    injected_sys_context = recording_agent.received_histories[0][0]["content"]
    assert "High-Converting Video Duration" in injected_sys_context
    assert "Keep product demo videos to 15 seconds" in injected_sys_context

    # 7. Strict Owner Isolation: Bob executes turn and DOES NOT receive Alice's knowledge
    recording_agent.received_histories.clear()
    request_bob = AgentTurnRequest(
        principal=PrincipalContext(actor_id="bob_cli", owner_user_id="owner_bob", channel="cli", session_id="sess_bob"),
        turn_id="turn_bob_1",
        message="Create a TikTok video outline for our product demo",
    )
    asyncio.run(_run_turn(request_bob))
    assert len(recording_agent.received_histories) == 1
    bob_history = recording_agent.received_histories[0]
    # No system context or empty
    if bob_history and bob_history[0].get("role") == "system":
        assert "High-Converting Video Duration" not in bob_history[0]["content"]

    # 8. Rollback v1 -> status becomes revoked, subsequent turns DO NOT receive it
    rb_result = promotion_service.rollback(v1.version_id, owner_user_id="owner_alice", expected_version=1)
    assert rb_result.revoked_version_id == v1.version_id
    assert rb_result.active_version_id is None

    recording_agent.received_histories.clear()
    request_alice_2 = AgentTurnRequest(
        principal=PrincipalContext(actor_id="alice_cli", owner_user_id="owner_alice", channel="cli", session_id="sess_alice"),
        turn_id="turn_alice_2",
        message="Create another TikTok video outline",
    )
    asyncio.run(_run_turn(request_alice_2))
    assert len(recording_agent.received_histories) == 1
    alice_history_2 = recording_agent.received_histories[0]
    if alice_history_2 and alice_history_2[0].get("role") == "system":
        assert "High-Converting Video Duration" not in alice_history_2[0]["content"]

    # 9. Procedural skill projection and rollback
    proc_evidence = EvidenceRef(
        evidence_id="ev_proc_1",
        source_type="workflow",
        source_id="wf_pr_100",
        digest="sha256:abc11223344",
        excerpt="Competitor analysis shows 15-second product demo has highest conversion.",
        polarity="positive",
    )
    proc_cand = LearningCandidate(
        candidate_id="cand_proc_e2e",
        owner_user_id="owner_alice",
        kind="procedure",
        title="TikTok Ad Generation Procedure",
        content="Step 1: Ingest product URL. Step 2: Extract key hooks. Step 3: Render 15s video.",
        evidence=(proc_evidence,),
        status="approved",
    )

    repository.create_candidate(proc_cand)
    proc_v1 = repository.create_version("cand_proc_e2e", proc_cand.content)
    skill_file = skill_publisher.publish(proc_cand, proc_v1)
    assert skill_file.exists()
    assert "name: tiktok-ad-generation-procedure" in skill_file.read_text(encoding="utf-8")

    # Rollback skill projection
    rolled_back_skill = skill_publisher.rollback("tiktok-ad-generation-procedure")
    assert rolled_back_skill is None
    assert not skill_file.exists()

    # 10. Metrics recording and effectiveness measurement
    assert metrics_engine.calculate_effectiveness("v1").status == "insufficient_data"

    for i in range(4):
        metrics_engine.record_metric(
            LearningExecutionMetric(
                metric_id=f"m_{i}",
                version_id="v_measured",
                workflow_type="product_video",
                success=True,
                corrections_count=0,
                approved=True,
                latency_ms=1200.0 + (i * 100),
                cost_minor_units=50,
            )
        )

    summary = metrics_engine.calculate_effectiveness("v_measured")
    assert summary.status == "measured"
    assert summary.sample_count == 4
    assert summary.success_rate == 1.0
    assert summary.approval_rate == 1.0
    assert summary.p50_latency_ms is not None
