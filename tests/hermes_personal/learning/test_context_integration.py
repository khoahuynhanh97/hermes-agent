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
from hermes_personal.learning.models import (
    EvidenceRef,
    LearningCandidate,
)
from hermes_personal.learning.repository import LearningRepository
from hermes_personal.learning.retrieval import ApprovedLearningRetriever
from hermes_personal.orchestration.event_repository import EventRepository
from hermes_personal.orchestration.ports import AgentOutput
from hermes_personal.orchestration.turn_service import HermesTurnService
from hermes_personal.sessions import SessionRepository
from hermes_personal.storage.sqlite import connect as sqlite_connect


class FakeTranscript:
    def __init__(self):
        self.events = []
        self.user_turns = []

    @property
    def history(self) -> tuple[Mapping[str, Any], ...]:
        user_msgs = [{"role": "user", "content": text} for text in self.user_turns]
        return tuple(user_msgs)

    def append_user_turn(self, text: str) -> None:
        self.user_turns.append(text)

    def append_event(self, event: Any) -> None:
        self.events.append(event)


class FakeTranscriptFactory:
    def __init__(self):
        self.transcript = FakeTranscript()

    def for_session(self, session_id: str) -> FakeTranscript:
        return self.transcript



class SpyAgent:
    def __init__(self):
        self.received_histories: list[tuple[Mapping[str, Any], ...]] = []
        self.received_requests: list[AgentTurnRequest] = []

    def run(self, request: AgentTurnRequest, history: tuple[Mapping[str, Any], ...]):
        self.received_requests.append(request)
        self.received_histories.append(history)
        yield AgentOutput("text_delta", {"text": "Hello from spy agent"})
        yield AgentOutput("completed", {"status": "success"})


@pytest.fixture
def db_conn(tmp_path):
    conn = sqlite_connect(tmp_path / "context_test.db")
    conn.execute("INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) VALUES ('user1', 'User One', '2026-08-24T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO channel_identity (channel, external_subject, owner_user_id, created_at) VALUES ('cli', 'user1', 'user1', '2026-08-24T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO conversation_session (session_id, owner_user_id, channel, external_conversation_id, created_at, updated_at) VALUES ('sess_1', 'user1', 'cli', 'ext_1', '2026-08-24T00:00:00Z', '2026-08-24T00:00:00Z')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def repository(db_conn):
    return LearningRepository(db_conn)


@pytest.fixture
def retriever(repository):
    return ApprovedLearningRetriever(repository)


@pytest.fixture
def assembler(retriever):
    return AgentContextAssembler(retriever)


import uuid


def sample_evidence(evidence_id: str | None = None):
    return EvidenceRef(
        evidence_id=evidence_id or f"ev_{uuid.uuid4().hex[:8]}",
        source_type="turn",
        source_id="t1",
        digest="sha256:456",
        excerpt="evidence excerpt",
    )



def test_agent_context_assembly_and_turn_service_integration(db_conn, repository, assembler):
    # Add an approved preference and knowledge for user1
    cand_pref = LearningCandidate(
        candidate_id="c_p1",
        owner_user_id="user1",
        kind="preference",
        title="Concise Style",
        content="Keep answers under 3 sentences.",
        evidence=(sample_evidence(),),
        status="approved",
    )
    repository.create_candidate(cand_pref)
    repository.create_version("c_p1", "Keep answers under 3 sentences.")

    cand_know = LearningCandidate(
        candidate_id="c_k1",
        owner_user_id="user1",
        kind="knowledge",
        title="Video Product Hook",
        content="Show the unboxing before the product benefit.",
        evidence=(sample_evidence(),),
        status="approved",
    )
    repository.create_candidate(cand_know)
    repository.create_version("c_k1", "Show the unboxing before the product benefit.")

    # Setup TurnService with context_assembler
    identity_repo = IdentityRepository(db_conn)

    session_repo = SessionRepository(db_conn)
    event_repo = EventRepository(db_conn)

    transcript_factory = FakeTranscriptFactory()
    spy_agent = SpyAgent()


    turn_service = HermesTurnService(
        identity_repository=identity_repo,
        session_repository=session_repo,
        event_repository=event_repo,
        transcript_factory=transcript_factory,
        agent=spy_agent,
        context_assembler=assembler,
    )

    request = AgentTurnRequest(
        principal=PrincipalContext(actor_id="user1", owner_user_id="user1", channel="cli", session_id="sess_1"),
        turn_id="turn_ctx_1",
        message="Help me write a Video Product Hook script",
    )




    async def _run():
        events = []
        async for event in turn_service.handle(request):
            events.append(event)
        return events

    events = asyncio.run(_run())
    assert len(events) >= 2
    assert any(e.event_type == "completed" for e in events)

    # Verify spy agent received the assembled context
    assert len(spy_agent.received_histories) == 1
    passed_history = spy_agent.received_histories[0]
    assert len(passed_history) >= 1
    system_msg = passed_history[0]
    assert system_msg["role"] == "system"
    assert "Concise Style" in system_msg["content"]
    assert "Video Product Hook" in system_msg["content"]
    assert "Show the unboxing before the product benefit." in system_msg["content"]
