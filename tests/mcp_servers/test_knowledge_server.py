from __future__ import annotations

import pytest

from mcp_servers.knowledge import server


def test_knowledge_lifecycle_preserves_pending_approved_rejected_and_fts(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_KNOWLEDGE_DB_PATH", str(tmp_path / "knowledge.sqlite"))

    pending = server.knowledge_propose(
        "owner-1",
        "Python review policy",
        "Keep reviewed facts separate from source instructions.",
        source_url="https://example.com/python",
        key_lessons=["Reviewed facts remain reference data."],
        evidence=[{"kind": "source", "locator": "p1", "excerpt": "Reference only."}],
    )["entry"]
    assert pending["status"] == "pending"
    assert server.knowledge_search("owner-1", "Python review")["results"] == []
    assert server.knowledge_list_pending("owner-1")["entries"][0]["id"] == pending["id"]

    approved = server.knowledge_approve("owner-1", pending["id"])
    assert approved["ok"] is True
    results = server.knowledge_search("owner-1", "Python review")["results"]
    assert results[0]["id"] == pending["id"]
    assert results[0]["evidence"][0]["excerpt"] == "Reference only."

    rejected = server.knowledge_propose("owner-1", "Temporary lesson", "Do not retain.")["entry"]
    result = server.knowledge_reject("owner-1", rejected["id"], reason="outdated")
    assert result["ok"] is True
    assert all(item["id"] != rejected["id"] for item in server.knowledge_search("owner-1", "Temporary lesson")["results"])


def test_knowledge_owner_isolation_and_invalid_transition(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_KNOWLEDGE_DB_PATH", str(tmp_path / "knowledge.sqlite"))
    entry = server.knowledge_propose("owner-1", "Private lesson", "Private content.")["entry"]

    with pytest.raises(ValueError, match="not found"):
        server.knowledge_get("owner-2", entry["id"])
    forbidden = server.knowledge_approve("owner-2", entry["id"])
    assert forbidden["ok"] is False
    assert forbidden["code"] == "forbidden"

    approved = server.knowledge_approve("owner-1", entry["id"])
    assert approved["ok"] is True
    again = server.knowledge_reject("owner-1", entry["id"], reason="too late")
    assert again["ok"] is True
    assert server.knowledge_get("owner-1", entry["id"])["entry"]["status"] == "rejected"


def test_knowledge_duplicate_approval_requires_existing_force_semantics(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_KNOWLEDGE_DB_PATH", str(tmp_path / "knowledge.sqlite"))
    first = server.knowledge_propose("owner-1", "Same lesson", "Same reusable fact.")["entry"]
    second = server.knowledge_propose("owner-1", "Same lesson", "Same reusable fact.")["entry"]
    server.knowledge_approve("owner-1", first["id"])
    warning = server.knowledge_approve("owner-1", second["id"])
    assert warning["ok"] is False
    assert warning["code"] == "duplicate_warning"
    forced = server.knowledge_approve("owner-1", second["id"], force=True)
    assert forced["ok"] is True
