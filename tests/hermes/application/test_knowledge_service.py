import pytest
from hermes.application.knowledge_service import KnowledgeService
from hermes.ports.knowledge_repository import KnowledgeRepository
from hermes.domain.results import Result


class InMemoryKnowledgeRepository(KnowledgeRepository):
    def __init__(self):
        self.proposals = {}

    def save(self, proposal):
        self.proposals[proposal["id"]] = proposal
        return Result.success(proposal)

    def get(self, proposal_id):
        proposal = self.proposals.get(proposal_id)
        if proposal:
            return Result.success(proposal)
        return Result.failure("not_found", f"Proposal {proposal_id} not found")

    def search(self, query):
        results = [p for p in self.proposals.values() 
                   if query.lower() in p.get("title", "").lower() 
                   and p.get("status") == "approved"]
        return Result.success(results)

    def list_by_status(self, status):
        results = [p for p in self.proposals.values() if p.get("status") == status]
        return Result.success(results)


@pytest.fixture
def repo():
    return InMemoryKnowledgeRepository()


@pytest.fixture
def service(repo):
    return KnowledgeService(repo)


def test_approved_knowledge_is_searchable_but_rejected_proposal_is_not(service, repo):
    # Create and approve first proposal
    proposal_result = service.propose("Python Tutorial", "http://example.com")
    assert proposal_result.ok
    proposal_id = proposal_result.value["id"]

    # Approve the proposal
    approve_result = service.approve(proposal_id)
    assert approve_result.ok

    # Search should find it
    search_result = service.search("Python")
    assert search_result.ok
    assert len(search_result.value) == 1

    # Create and reject another proposal
    proposal2_result = service.propose("Java Tutorial", "http://example2.com")
    proposal2_id = proposal2_result.value["id"]
    service.reject(proposal2_id)

    # Search should only find the approved one (Python)
    search2_result = service.search("Tutorial")
    assert len(search2_result.value) == 1
    assert search2_result.value[0]["title"] == "Python Tutorial"


def test_propose_creates_pending_knowledge(service):
    result = service.propose("New Lesson", "http://example.com", "technology")
    assert result.ok
    assert result.value["status"] == "pending"
    assert result.value["title"] == "New Lesson"


def test_list_pending_only_returns_pending(service):
    service.propose("P1", "s1")
    service.propose("P2", "s2")
    p3 = service.propose("P3", "s3").value
    service.approve(p3["id"])

    pending = service.list_pending()
    assert pending.ok
    assert len(pending.value) == 2
