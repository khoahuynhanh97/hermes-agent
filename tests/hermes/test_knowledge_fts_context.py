from __future__ import annotations


def test_approved_context_uses_fts_without_nonexistent_is_current_column(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_DB_PATH", str(tmp_path / "hermes.db"))

    from hermes.knowledge_legacy import SQLiteKnowledgeStore

    store = SQLiteKnowledgeStore(default_owner_user_id="5069349064")
    lesson = store.add_entry(
        title="AI GitHub repositories for Hermes",
        key_lessons=["Use an AI repository after human review."],
        detail_data={"summary": "Use reviewed repositories for AI agents."},
        owner_user_id="5069349064",
    )
    store.mark_approved(lesson["id"], approved_by="5069349064", approval_mode="test")

    context = store.get_approved_context("repo github AI", owner_user_id="5069349064")

    assert "AI GitHub repositories for Hermes" in context
