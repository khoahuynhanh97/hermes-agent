from __future__ import annotations

import pytest

from hermes_personal.integrations.knowledge import (
    KnowledgeEdgeCapability,
    create_knowledge_mcp,
)
from hermes_personal.learning.context import AgentContextAssembler
from hermes_personal.learning.evaluator import CandidateEvaluator
from hermes_personal.learning.models import (
    EvidenceRef,
    LearningCandidate,
)
from hermes_personal.learning.promotion import PromotionService
from hermes_personal.learning.repository import LearningRepository
from hermes_personal.learning.retrieval import ApprovedLearningRetriever
from hermes_personal.storage.sqlite import connect as sqlite_connect
from hermes_personal.workflows.approvals import ApprovalService


@pytest.fixture
def db_conn(tmp_path):
    conn = sqlite_connect(tmp_path / "knowledge_p0.db")
    conn.execute(
        "INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) "
        "VALUES ('user_alice', 'Alice', '2026-08-24T00:00:00Z')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) "
        "VALUES ('user_bob', 'Bob', '2026-08-24T00:00:00Z')"
    )
    conn.commit()
    yield conn
    conn.close()


def test_knowledge_p0_full_lifecycle(db_conn):
    """Test full P0 lifecycle:
    1. Knowledge candidate creation (auto-evaluated -> pending_approval)
    2. ApprovalService wiring + approve_candidate -> active version & FTS5 index
    3. FTS5-based search & Vietnamese keyword retrieval
    4. Provenance rendering in AgentContextAssembler
    """
    repository = LearningRepository(db_conn)
    retriever = ApprovedLearningRetriever(repository)
    approval_service = ApprovalService(db_conn)
    promotion_service = PromotionService(repository, approval_service=approval_service)

    capability = KnowledgeEdgeCapability(
        repository=repository,
        retriever=retriever,
        promotion_service=promotion_service,
        default_owner_user_id="user_alice",
        approval_service=approval_service,
    )

    # 1. Create candidate via capability (simulating /hoc TikTok capture)
    create_res = capability.create_candidate(
        owner_user_id="user_alice",
        title="Chiến lược SEO TikTok Shop 2026",
        content="Tối ưu 5 từ khóa trong tiêu đề và gắn hashtag ngách để tăng 40% organic reach.",
        kind="knowledge",
        evidence=[
            {
                "source_type": "turn",
                "source_id": "https://vt.tiktok.com/ZS6xxxxxx/",
                "excerpt": "Phân tích 100 video TikTok Shop cho thấy tối ưu 5 từ khóa giúp tăng 40% reach.",
            }
        ],
    )

    candidate_id = create_res["candidate_id"]
    assert create_res["status"] == "pending_approval"
    assert create_res["approval_id"] is not None

    # Before approval, retrieval returns nothing
    unapproved_retrieval = retriever.retrieve(owner_user_id="user_alice", query="SEO TikTok Shop")
    assert len(unapproved_retrieval) == 0

    # 2. Approve candidate (simulating user tapping [Duyệt] on Telegram)
    approve_res = capability.approve_candidate(candidate_id, owner_user_id="user_alice")
    assert approve_res["status"] == "approved"
    assert approve_res["version"] == 1

    # 3. Retrieve via FTS5 / ApprovedLearningRetriever
    retrieved = retriever.retrieve(
        owner_user_id="user_alice",
        query="Chiến lược SEO TikTok",
        limit=5,
    )
    assert len(retrieved) == 1
    item = retrieved[0]
    assert item.candidate_id == candidate_id
    assert item.title == "Chiến lược SEO TikTok Shop 2026"
    assert item.source_ref == "https://vt.tiktok.com/ZS6xxxxxx/"
    assert "tối ưu 5 từ khóa" in item.evidence_excerpt.lower()

    # Verify owner isolation: user_bob cannot retrieve user_alice's knowledge
    bob_retrieval = retriever.retrieve(owner_user_id="user_bob", query="SEO TikTok Shop")
    assert len(bob_retrieval) == 0

    # 4. Context assembly with provenance
    assembler = AgentContextAssembler(retriever)
    from hermes_personal.contracts import AgentTurnRequest, PrincipalContext

    turn_req = AgentTurnRequest(
        principal=PrincipalContext(
            actor_id="alice_tg",
            owner_user_id="user_alice",
            channel="telegram",
            session_id="tg_sess_1",
        ),
        message="Làm thế nào để tăng organic reach trên TikTok Shop?",
        turn_id="turn_1",
    )

    ctx = assembler.assemble(turn_req, history=())
    sys_prompt = ctx.build_system_context()

    assert "## Approved Knowledge" in sys_prompt
    assert "Chiến lược SEO TikTok Shop 2026" in sys_prompt
    assert "Source: https://vt.tiktok.com/ZS6xxxxxx/" in sys_prompt
    assert f"ID: {candidate_id}" in sys_prompt


def test_knowledge_p0_reject_flow(db_conn):
    """Test rejecting a knowledge candidate."""
    repository = LearningRepository(db_conn)
    retriever = ApprovedLearningRetriever(repository)
    approval_service = ApprovalService(db_conn)
    promotion_service = PromotionService(repository, approval_service=approval_service)

    capability = KnowledgeEdgeCapability(
        repository=repository,
        retriever=retriever,
        promotion_service=promotion_service,
        default_owner_user_id="user_alice",
        approval_service=approval_service,
    )

    create_res = capability.create_candidate(
        owner_user_id="user_alice",
        title="Spam Technique",
        content="Post 100 times per hour to trick algorithm.",
        kind="knowledge",
    )
    candidate_id = create_res["candidate_id"]

    reject_res = capability.reject_candidate(
        candidate_id,
        owner_user_id="user_alice",
        reason="Violates community guidelines",
    )
    assert reject_res["status"] == "rejected"

    cand = repository.get_candidate(candidate_id)
    assert cand.status == "rejected"

    retrieved = retriever.retrieve(owner_user_id="user_alice", query="Spam Technique")
    assert len(retrieved) == 0
